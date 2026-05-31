"""HTTP access to the Cali IDESC GeoServer WFS.

The single quirk that matters: the server advertises only GML 3.2 as an output
format, but ``outputFormat=application/json`` works and is far easier to consume.
The *other* quirk (the one that silently corrupts data) is that a single
unpaged request can return a 500 MB blob that times out mid-parse — so we always
page with ``count``/``startIndex`` and reconcile the running total against the
server's authoritative ``numberMatched``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import dagster as dg
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import WFS_BASE_URL, WFS_VERSION


@dataclass
class DownloadResult:
    """Outcome of a GetFeature download, per the server's own tally."""

    number_matched: int  # features the server says match the query
    number_returned: int  # features the server says it actually sent
    bytes_written: int

    @property
    def complete(self) -> bool:
        return self.number_matched == self.number_returned


class WfsResource(dg.ConfigurableResource):
    """Thin WFS client with retries and paged GeoJSON download."""

    base_url: str = WFS_BASE_URL
    timeout: int = 180
    max_retries: int = 4
    page_size: int = 10_000

    def _session(self) -> requests.Session:
        retry = Retry(
            total=self.max_retries,
            connect=self.max_retries,
            read=self.max_retries,
            status=self.max_retries,
            backoff_factor=1.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
            raise_on_status=False,
        )
        s = requests.Session()
        adapter = HTTPAdapter(max_retries=retry)
        s.mount("http://", adapter)
        s.mount("https://", adapter)
        return s

    def _get(self, session: requests.Session, params: dict) -> requests.Response:
        base = {"service": "WFS", "version": WFS_VERSION}
        resp = session.get(
            self.base_url,
            params={**base, **params},
            timeout=self.timeout,
            allow_redirects=True,  # http 301 -> https
        )
        resp.raise_for_status()
        return resp

    # -- capabilities ---------------------------------------------------------
    def get_capabilities_xml(self, workspace: str | None = None) -> bytes:
        """WFS GetCapabilities for the whole server, or one workspace endpoint."""
        url = (
            self.base_url
            if workspace is None
            else self.base_url.replace("/ows", f"/{workspace}/ows")
        )
        with self._session() as s:
            resp = s.get(
                url,
                params={
                    "service": "WFS",
                    "version": WFS_VERSION,
                    "request": "GetCapabilities",
                },
                timeout=self.timeout,
                allow_redirects=True,
            )
            resp.raise_for_status()
            return resp.content

    # -- counts ---------------------------------------------------------------
    def count_features(self, typename: str) -> int:
        """Authoritative feature count via ``resultType=hits`` (cheap)."""
        with self._session() as s:
            resp = self._get(
                s,
                {"request": "GetFeature", "typeNames": typename, "resultType": "hits"},
            )
        return _number_matched_from_xml(resp.content)

    # -- download -------------------------------------------------------------
    def download_geojson(self, typename: str, dest: Path) -> DownloadResult:
        """Stream the full GeoJSON FeatureCollection for ``typename`` to ``dest``.

        We do NOT use ``startIndex`` paging: many layers are PK-less SQL views and
        GeoServer rejects index paging on them ("cannot do natural order without a
        primary key"). Instead we ask for the whole layer in one request and stream
        it to disk in chunks (so a 500 MB response never lands in memory). The
        server stamps ``numberMatched``/``numberReturned`` into the JSON tail, which
        we read back to prove the payload arrived whole.
        """
        dest.parent.mkdir(parents=True, exist_ok=True)
        base = {"service": "WFS", "version": WFS_VERSION}
        params = {
            **base,
            "request": "GetFeature",
            "typeNames": typename,
            "outputFormat": "application/json",
        }
        nbytes = 0
        with self._session() as s:
            with s.get(
                self.base_url,
                params=params,
                timeout=self.timeout,
                allow_redirects=True,
                stream=True,
            ) as resp:
                resp.raise_for_status()
                ctype = resp.headers.get("content-type", "")
                if "json" not in ctype.lower():
                    raise RuntimeError(
                        f"WFS layer {typename!r} did not return JSON "
                        f"(content-type={ctype!r}); may need a GML fallback. "
                        f"Body starts: {resp.text[:300]!r}"
                    )
                with dest.open("wb") as fh:
                    for chunk in resp.iter_content(chunk_size=1 << 16):
                        if chunk:
                            fh.write(chunk)
                            nbytes += len(chunk)
        matched, returned = _counts_from_tail(dest)
        return DownloadResult(
            number_matched=matched, number_returned=returned, bytes_written=nbytes
        )


_NUM_MATCHED = re.compile(rb'"numberMatched"\s*:\s*(\d+|"unknown")')
_NUM_RETURNED = re.compile(rb'"numberReturned"\s*:\s*(\d+)')


def _counts_from_tail(path: Path, tail_bytes: int = 4096) -> tuple[int, int]:
    """Read GeoServer's ``numberMatched``/``numberReturned`` from the JSON tail."""
    size = path.stat().st_size
    with path.open("rb") as fh:
        fh.seek(max(0, size - tail_bytes))
        tail = fh.read()
    m = _NUM_MATCHED.search(tail)
    r = _NUM_RETURNED.search(tail)
    if not r:
        raise RuntimeError(f"Could not find numberReturned in tail of {path}")
    returned = int(r.group(1))
    if m and m.group(1) != b'"unknown"':
        matched = int(m.group(1))
    else:
        # Server reported "unknown" — fall back to what it actually returned.
        matched = returned
    return matched, returned


def _number_matched_from_xml(xml: bytes) -> int:
    """Pull ``numberMatched`` from a WFS hits response without a full parse."""
    from lxml import etree

    root = etree.fromstring(xml)
    val = root.get("numberMatched")
    if val is None or val == "unknown":
        raise RuntimeError(f"WFS hits response missing numberMatched: {xml[:200]!r}")
    return int(val)


@dg.definitions
def resources() -> dg.Definitions:
    return dg.Definitions(resources={"wfs": WfsResource()})
