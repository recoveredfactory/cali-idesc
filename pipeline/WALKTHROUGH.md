# Dagster, on screen — a 10-minute walkthrough

A presenter's talk-track for `dg dev` (http://localhost:3000). Each section is
"point at this, say this." The whole arc: **one graph, built two ways.**

---

## 0. Set the frame (before clicking anything)

> "A data pipeline is just: get data, shape it, publish it. Dagster lets us
> declare each step as an **asset** — a thing that exists — and then it draws the
> map, runs the steps in order, and checks our work."

Open **Assets → View global asset lineage**. The whole pipeline is on screen.

---

## 1. Read the map (the lineage graph)

Point at the graph and name the three things students are seeing:

- **Boxes = assets.** Each is a real artifact (a catalog, a GeoJSON, a manifest).
- **Arrows = dependencies.** "Do this one first." Dagster derives the order from
  these — we never write a schedule of steps by hand.
- **Colored clusters = groups.** `catalog`, `layers`, `manifest`, `featured`.

Trace one path out loud:

```
wfs_catalog ──► layer_geojson ──► layer_pmtiles ──► viewer_manifest
```

> "`wfs_catalog` asks Cali's server what exists — 357 layers. Everything
> downstream flows from that one root."

---

## 2. An asset up close

Click **`wfs_catalog`**. In the side panel, point at:

- **Description** — plain English, written right on the asset.
- **Metadata** from its last run — number of layers, workspaces. "The pipeline
  reports on itself."
- **Checks** — e.g. `no_missing_layers`. A green check = "we verified this,
  not just ran it."

> "An asset isn't a script that ran. It's a thing that *exists*, with a
> description, freshness, metadata, and quality checks attached."

---

## 3. The same idea, written in YAML (the 'wow')

Point at the **`featured`** group — four boxes, all hanging off `wfs_catalog`.

> "We did NOT write four Python functions for these. We wrote the behavior
> **once** — a *component* — and then declared four layers in YAML."

Show the two files side by side:

- `src/cali_geo/components/wfs_layer_set.py` — the behavior, written once.
- `src/cali_geo/defs/featured_layers/defs.yaml` — the four layers, in YAML.

The live moment:

1. Add three lines to `defs.yaml` (one more `- typename: ...`).
2. Back in the UI, **Reload definitions**.
3. A **fifth box appears** in `featured`. No Python was written.

> "Code defines the *how*. YAML defines the *what*. Add a layer = add three
> lines. And notice — the YAML asset depends on `wfs_catalog`, the same as the
> hand-written ones. Components aren't a separate island; it's one graph."

---

## 4. Run it, and trust it

Select **`idesc__mc_comunas`** → **Materialize**.

Watch the run, then point at the result:

- The check **`has_features` turns green.**
- Metadata says **`feature_count: 22`** — Cali has 22 comunas. Correct.

> "It didn't just run. It ran, recorded what it produced, and **proved** the
> result was sane. That green check is the difference between 'the script
> finished' and 'the data is right.'"

---

## The one-sentence takeaway

> **Assets** are your data as a map; **dependencies** are the order; **checks**
> are the trust; and **components** let you stamp out the same asset from YAML.
> That's Dagster — and it's going to rule your data world.
