"""``layer_translations`` — English versions of every layer's title + abstract.

The published metadata is Spanish (the primary language of the outputs). This
asset produces an English companion for each layer via the Anthropic API, cached
to ``data/translations.json`` and keyed by a hash of the Spanish source so only
new or changed layers are re-translated. Field/attribute names are out of scope.
"""

import hashlib
import json
import os
import re

import dagster as dg
from dagster import AssetExecutionContext

from .catalog import wfs_catalog
from .config import Paths

TRANSLATE_MODEL = "claude-sonnet-4-6"
BATCH_SIZE = 40

_SYSTEM = (
    "You translate Colombian Spanish GIS/cadastral layer metadata into clear, "
    "concise English for a data catalog. Preserve proper nouns and standard GIS "
    "terms. Do not add commentary. You will receive a JSON array of objects with "
    "fields key, title_es, abstract_es. Return ONLY a JSON array of objects with "
    "fields key, title_en, abstract_en — same keys, same order, nothing else."
)


def _src_hash(title_es: str, abstract_es: str) -> str:
    return hashlib.sha256(f"{title_es}␟{abstract_es}".encode()).hexdigest()[:16]


def _extract_json_array(text: str) -> list[dict]:
    """Tolerantly pull a JSON array out of a model response."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text).strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON array in response: {text[:200]!r}")
    return json.loads(text[start : end + 1])


def _translate_batch(client, items: list[dict]) -> dict[str, dict]:
    payload = [
        {"key": it["key"], "title_es": it["title_es"], "abstract_es": it["abstract_es"]}
        for it in items
    ]
    msg = client.messages.create(
        model=TRANSLATE_MODEL,
        max_tokens=8192,
        system=[{"type": "text", "text": _SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
    )
    text = "".join(block.text for block in msg.content if block.type == "text")
    out = {}
    for row in _extract_json_array(text):
        out[row["key"]] = {
            "title_en": (row.get("title_en") or "").strip(),
            "abstract_en": (row.get("abstract_en") or "").strip(),
        }
    return out


@dg.asset(
    deps=[wfs_catalog],
    group_name="catalog",
    description="English title/abstract for every layer (Anthropic, cached by source hash).",
)
def layer_translations(context: AssetExecutionContext) -> dg.MaterializeResult:
    records = json.loads(Paths.catalog.read_text(encoding="utf-8"))
    cache: dict[str, dict] = {}
    if Paths.translations.exists():
        cache = json.loads(Paths.translations.read_text(encoding="utf-8"))

    stale = []
    for r in records:
        h = _src_hash(r.get("title_es", ""), r.get("abstract_es", ""))
        if cache.get(r["key"], {}).get("src_hash") != h:
            stale.append({**r, "_hash": h})

    if not stale:
        context.log.info("translations cache is up to date")
        return dg.MaterializeResult(
            metadata={"translated": 0, "cached": len(cache), "total": len(records)}
        )

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise dg.Failure(
            description=(
                "ANTHROPIC_API_KEY is not set; cannot translate "
                f"{len(stale)} layer(s). Set it and re-materialize."
            )
        )

    import anthropic

    client = anthropic.Anthropic()
    translated = 0
    for i in range(0, len(stale), BATCH_SIZE):
        batch = stale[i : i + BATCH_SIZE]
        try:
            result = _translate_batch(client, batch)
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            context.log.warning(f"batch {i // BATCH_SIZE} failed to parse: {exc}")
            continue
        for item in batch:
            tr = result.get(item["key"])
            if tr is None:
                continue
            cache[item["key"]] = {
                "src_hash": item["_hash"],
                "title_en": tr["title_en"],
                "abstract_en": tr["abstract_en"],
            }
            translated += 1
        context.log.info(f"translated {min(i + BATCH_SIZE, len(stale))}/{len(stale)}")

    Paths.translations.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return dg.MaterializeResult(
        metadata={
            "translated": translated,
            "cached": len(cache),
            "total": len(records),
            "sample": dg.MetadataValue.json(
                {k: cache[k] for k in list(cache)[:3]} if cache else {}
            ),
        }
    )
