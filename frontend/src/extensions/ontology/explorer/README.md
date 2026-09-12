# explorer/ — Vendored Semantica Explorer graph core

Vendored from **[semantica-agi/semantica](https://github.com/semantica-agi/semantica)** `explorer/` app (MIT license).

- **Pinned SHA:** `7057387775ecdf74c14e38d0067fd8e1267eaaf8` (repo HEAD at vendoring time, 2026-09-12)
- **License:** MIT (upstream `explorer/` inherits repo LICENSE)
- **EAI-CUSTOM plan:** `docs/superpowers/plans/2026-09-12-ontology-semantic-map-ui.md` Task 2

## Vendored file inventory (24 files)

Core (plan Step 2.3, upstream path → local path; all under `explorer/src/` upstream):

| Upstream | Local |
| --- | --- |
| `store/graphStore.ts` | `graphStore.ts` |
| `store/edgePairKeys.js` + `edgePairKeys.d.ts` | `edgePairKeys.ts` (merged) |
| `workspaces/GraphWorkspace/GraphCanvas.tsx` | `GraphCanvas.tsx` |
| `workspaces/GraphWorkspace/sigmaNativeRendering.ts` | `sigmaNativeRendering.ts` |
| `workspaces/GraphWorkspace/useLoadGraph.ts` | `useLoadGraph.ts` |
| `workspaces/GraphWorkspace/smallGraphLayout.ts` | `smallGraphLayout.ts` |

Dependency closure (added per type-closure rule; all under `explorer/src/workspaces/GraphWorkspace/` upstream):

`graphTheme.ts`, `graphEntityShape.ts`, `graphLoading.ts`, `types.ts`, `scene.ts`,
`graphSceneLayers.ts`, `graphSceneState.ts`, `graphStructureLayer.ts`, `graphAnalytics.ts`,
`graphColorLegend.ts`, `behaviors/{types,clickSelectionBehavior,fitViewBehavior,focusCameraBehavior,hoverActivationBehavior,pathHighlightBehavior,searchFocusBehavior,viewModeSwitchBehavior}.ts`

Internal import paths were rewritten to the flat local layout
(`../../store/graphStore` → `./graphStore`, `../../../store/graphStore` → `../graphStore`,
`../workspaces/GraphWorkspace/graphTheme` → `./graphTheme`, `./edgePairKeys.js` → `./edgePairKeys`).

## Dependencies (ranges from upstream `explorer/package.json`)

`sigma@^3.0.3`, `@sigma/edge-curve@^3.1.0`, `graphology@^0.26.0`,
`graphology-communities-louvain@^2.0.2`, `graphology-layout-forceatlas2@^0.10.1`,
`graphology-metrics@^2.4.2`, `graphology-shortest-path@^2.1.0`.

注：sigma/graphology-metrics 取 semver 兼容的较新 range（`^3.0.3`/`^2.4.2`，均为上游 range `^3.0.2`/`^2.4.0` 的子集，pnpm 安装时落到当时最新匹配版），其余照抄上游。
(`@sigma/node-border` not vendored — nothing in the closure imports it.
`@tanstack/react-query`, `react` already present in this repo.)

## Strip records (plan Step 2.5)

Audit result: **0 imports removed** — the vendored type-closure never reaches any
Explorer-specific subsystem. Grep over this directory finds zero references to
`vis-timeline`, timeline panels, markdown resources, decisions callbacks,
provenance reports, `semantic-neighborhood`/embeddings, `/api/info` capability
probing, or plugin registry.

Kept deliberately (inert data vocabulary, not subsystem imports): node-attribute
keys such as `valid_from` / `valid_until` / `temporalRange` and the
`PROVENANCE_KEYS` property list in `useLoadGraph.ts` (`source`, `pmid`,
`confidence`, …). This system's data simply leaves them empty; rendering is
unaffected. Files touched by this vocabulary: `GraphCanvas.tsx`, `useLoadGraph.ts`,
`types.ts`, `scene.ts`, `graphTheme.ts`, `graphSceneLayers.ts`, `graphSceneState.ts`.

## Vendoring adaptations (recorded per Step 2.8)

1. `edgePairKeys.js` + `.d.ts` merged into `edgePairKeys.ts` (upstream ships a JS
   module with a sibling declaration file; a single `.ts` keeps the flat layout valid).
2. Vite `import.meta.env.DEV` → `process.env.NODE_ENV === "development"` (3 sites:
   `GraphCanvas.tsx` x2, `graphSceneState.ts` x1). Semantically equal debug flag.
3. `noUncheckedIndexedAccess` guards (this repo's tsconfig is stricter than
   upstream's, which is `strict` without that flag): `GraphCanvas.tsx` loop guard,
   `useLoadGraph.ts` + `graphAnalytics.ts` total-index palette fallbacks,
   `smallGraphLayout.ts` sort/single-component guards. All no-ops at runtime.
4. `// @ts-nocheck` exemption (2 files, tighten later):
   - `graphSceneLayers.ts` (28 strictness-delta errors)
   - `graphSceneState.ts` (26 strictness-delta errors)
   All are index-access-possibly-undefined complaints from the same config delta —
   no type-level semantic conflicts.

## Not vendored (out of Task 2 scope)

Explorer workspaces other than the graph canvas (decisions, enrich, temporal
scrubber, markdown editor, ontology editor UI, GraphWorkspace.tsx shell,
SigmaSceneAdapter, GraphInspectorPanel, TimelinePanel) — the page shell (plan
Task 3) composes `GraphCanvas` with this system's own panels.
