# CAD Comprehension MCP Server

Standalone MCP server that turns DXF drawings into structured facts for the
fire-protection / EIA compliance skills and the Office-Word report pipeline.
Runs in its own container so heavy CAD deps (ezdxf, matplotlib) stay out of
the gateway image.

## Tool: `analyze_cad`

The agent sees this tool as **`cad_analyze_cad`** — the gateway's
`MultiServerMCPClient` prefixes every MCP tool with its server name
(`tool_name_prefix=True`) to avoid cross-server name collisions. The tool
description is unchanged, so the agent finds it by intent.

| arg | type | default | notes |
|-----|------|---------|-------|
| `file_path` | str | — | absolute or `/mnt/user-data/...` virtual path to a `.dxf` |
| `rasterize` | bool | `false` | also render a PNG preview. ~80s on large drawings |

Returns JSON: `{status, file, facts, raster_png?, warnings?}`.

`facts` = dxf_version, codepage, entity_count, entity_counts, layers[],
pipe_diameters[] (DN*), hydrant_risers[] (XL-*), axis_dimensions_mm_sample[],
text_samples[], extent.

## Run locally (no Docker)

```bash
pip install -r requirements.txt
MCP_TRANSPORT=streamable-http MCP_PORT=8003 python server.py
```

Self-check against a real DXF:

```bash
CAD_FIXTURE=/path/to/x.dxf python test_analyze.py
```

## Run in deer-flow (dev)

The `cad` service lives in `docker/docker-compose-dev.yaml` (dev startup uses
only that file — `scripts/docker.sh` → `docker compose -p eai-docker -f
docker-compose-dev.yaml`), so it comes up with the rest of dev:

```bash
make docker-start          # or: scripts/docker.sh start
```

Then enable the MCP server in `extensions_config.json` (`mcpServers.cad.enabled`
→ `true`) and restart the gateway so it picks up the tool:

```bash
docker compose -p eai-docker -f docker/docker-compose-dev.yaml restart gateway
```

The agent now has the `analyze_cad` tool via function calling.

> Production uses `docker/docker-compose.yaml` (+ overlays), not the dev file.
> Add a `cad` service there too when promoting beyond dev.

> **Build mirror (restricted networks):** pypi.org is slow/unreachable from
> some dev networks. The build reuses `UV_INDEX_URL` as the pip index, so build
> with a mirror: `UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple make docker-start`
> (or set `UV_INDEX_URL` in `.env` permanently — the backend/gateway build needs
> the same).

## Path contract

The agent is told uploads live at the sandbox virtual path
`/mnt/user-data/uploads/<name>` (set by `UploadsMiddleware`). That path is
thread-scoped and only the sandbox tools translate it — an MCP tool receives
it as a literal string, so it does **not** resolve by default.

`analyze_cad` bridges this: if the given path isn't found literally, and it's
a `/mnt/user-data/...` virtual path, the tool glob-searches the data root
(`CAD_DATA_ROOT=/data`, mounted from `DEER_FLOW_HOME`) as
`/data/users/*/threads/*/user-data/<rest>` and uses the first match.

So the agent can pass the virtual path it already knows:
`analyze_cad(file_path="/mnt/user-data/uploads/cad.dxf")`. A literal physical
path also works. **Ceiling:** the glob assumes the filename is unique across
threads; if two threads hold same-named files, pass an absolute path to
disambiguate. Upgrade path: carry `thread_id` via MCP context and resolve
directly.

## Encoding note

ezdxf decodes DXF Chinese (GBK) into correct Unicode — verified on the test
fixture (layer `器械` = U+5668 U+68B0). "Garbled" text you see in a Windows
console is a terminal-rendering artifact, not data loss; the JSON the agent
receives carries valid Chinese. ASCII facts (DN pipe sizes, XL riser numbers,
axis dimensions) survive even in the rare case of genuine on-disk codepage loss.

## Phase 1 limits (intentional)

- **DXF only.** DWG must be converted upstream (AutoCAD DXFOUT). ODA File
  Converter integration is deferred until a real DWG-without-DXF arrives.
- **One tool.** Geometry/compliance math (shapely: egress distance, compartment
  area) and per-layer raster tiling are phase 2.
- **Raster is opt-in.** matplotlib render is ~80s on a 34k-entity drawing; call
  `rasterize=true` only for the vision-based symbol-recognition step.
