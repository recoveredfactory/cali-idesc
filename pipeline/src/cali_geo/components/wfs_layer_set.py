"""``WfsLayerSet`` — a teaching Component (the "New Way").

This is the same idea as the hand-written assets in ``cali_geo/defs/``, but
turned inside-out: instead of writing one Python function per layer, you write
the *behavior* once (this class) and then declare as many *instances* as you
like in YAML — no Python required to add a layer.

Where things live (the one rule to remember):

* Component **types** live here, under ``cali_geo/components/`` — registered by
  ``registry_modules = ["cali_geo.components.*"]`` in ``pyproject.toml``.
* Component **instances** live under ``cali_geo/defs/.../defs.yaml`` — those are
  what Dagster discovers and turns into the asset graph.

Each entry in the YAML ``layers:`` list becomes its own Dagster asset, complete
with metadata and an asset check, generated at load time. Open ``dg dev`` and
watch the graph fill in from the YAML.
"""

from collections.abc import Sequence

import dagster as dg
from dagster.components import Component, ComponentLoadContext, Model, Resolvable

# Reuse the *real* WFS client and key convention from the production pipeline —
# the component supplies behavior; it does not reinvent the data access.
from cali_geo.defs.config import partition_key
from cali_geo.defs.resources import WfsResource


class LayerSpec(Model, Resolvable):
    """One row of the YAML ``layers:`` list."""

    typename: str  # e.g. "idesc:mc_comunas" (workspace:layer)
    title: str | None = None


class WfsLayerSet(Component, Model, Resolvable):
    """Generate one asset per WFS layer that probes its live feature count.

    Example ``defs.yaml`` (this whole block is what a student edits):

    .. code-block:: yaml

        type: cali_geo.components.WfsLayerSet
        attributes:
          group_name: featured
          layers:
            - typename: idesc:mc_comunas
              title: Comunas de Cali
            - typename: idesc:mc_barrios
    """

    # These fields ARE the YAML schema — Resolvable derives a validated model
    # from them, so a typo in defs.yaml is a load-time error, not a 3am surprise.
    layers: Sequence[LayerSpec]
    group_name: str = "featured"

    def build_defs(self, context: ComponentLoadContext) -> dg.Definitions:
        return dg.Definitions(assets=[self._asset_for(spec) for spec in self.layers])

    def _asset_for(self, spec: LayerSpec) -> dg.AssetsDefinition:
        key = partition_key(spec.typename)  # "idesc:mc_comunas" -> "idesc__mc_comunas"

        @dg.asset(
            name=key,
            group_name=self.group_name,
            description=spec.title or f"Live WFS probe of {spec.typename}",
            check_specs=[
                dg.AssetCheckSpec(
                    name="has_features",
                    asset=key,
                    description="server reports at least one feature",
                )
            ],
        )
        def _probe(context: dg.AssetExecutionContext, wfs: WfsResource):
            # ``wfs`` is injected by key from cali_geo/defs/resources.py — the
            # component's assets share the same resource as the real pipeline.
            try:
                count = wfs.count_features(spec.typename)
                note = None
            except Exception as exc:  # noqa: BLE001 — surface, don't crash the graph
                count, note = 0, str(exc)
                context.log.warning(f"{spec.typename}: probe failed ({exc})")

            context.log.info(f"{spec.typename}: {count} features")
            return dg.MaterializeResult(
                metadata={
                    "typename": spec.typename,
                    "title": spec.title or spec.typename,
                    "feature_count": count,
                    **({"error": note} if note else {}),
                },
                check_results=[
                    dg.AssetCheckResult(
                        check_name="has_features",
                        passed=count > 0,
                        metadata={"feature_count": count},
                    )
                ],
            )

        return _probe
