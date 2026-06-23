# text-to-cad MCP Server

Standalone MCP server that turns agent-authored **build123d** Python source
into **STEP** (ISO 10303) files — the lossless interchange format every
mechanical CAD tool reads — plus optional STL. Runs in its own container so
the heavy CAD kernel (build123d + OCP/OpenCascade native libs, ~400MB+) stays
out of the gateway image.

This is the integration path for [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad)
into deer-flow: **CAD capability reaches the agent as an MCP tool from a
separate container**, not by polluting the gateway image. Mirrors the
existing `mcp-server/cad-mcp` pattern.

## Tool: `create_step`

The agent sees this tool as **`text-to-cad_create_step`** — the gateway's
`MultiServerMCPClient` prefixes every MCP tool with its server name
(`tool_name_prefix=True`) to avoid cross-server name collisions.

| arg | type | default | notes |
|-----|------|---------|-------|
| `source` | str | — | build123d Python; must bind final geometry to `result`. `build123d` pre-imported. Units: mm. |
| `output_path` | str | — | absolute path or `/mnt/user-data/outputs/<name>.step` virtual path |
| `also_stl` | bool | `false` | also write an STL (same basename) |

Returns JSON: `{status:"ok", step, stl?, volume_mm3?, bbox_mm?}` on success,
or `{status:"error", error, detail?}` on failure.

Example source (the agent authors this; the container executes it):

```python
with BuildPart() as p:
    Box(100, 60, 20)
    # four 8mm through-holes, 2mm chamfer on top, etc.
result = p.part
```

## Run locally (no Docker)

```bash
pip install -r requirements.txt   # build123d pulls OCP — heavy, first install is slow
MCP_TRANSPORT=streamable-http MCP_PORT=8004 python server.py
```

Self-check (generates a Box, asserts STEP + STL + bbox):

```bash
python test_step.py
```

## Run in deer-flow (dev)

The `text-to-cad` service lives in `docker/docker-compose-dev.yaml` (dev
startup uses only that file), so it comes up with the rest of dev:

```bash
make docker-start          # or: scripts/docker.sh start
```

Then enable the MCP server in `extensions_config.json`
(`mcpServers.text-to-cad.enabled` → `true`) and restart the gateway:

```bash
docker compose -p eai-docker -f docker/docker-compose-dev.yaml restart gateway
```

The agent now has the `text-to-cad_create_step` tool via function calling.

> Production uses `docker/docker-compose.yaml` (+ overlays), not the dev file.
> Add a `text-to-cad` service there too when promoting beyond dev.

> **Build mirror (restricted networks):** pypi.org is slow/unreachable from
> some dev networks, and OCP wheels are large. The build reuses `UV_INDEX_URL`
> as the pip index: `UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple make docker-start`
> (or set `UV_INDEX_URL` in `.env` permanently).

## Path contract

The agent writes outputs to the sandbox virtual path
`/mnt/user-data/outputs/<name>.step`. That path is thread-scoped and only
the sandbox tools translate it — an MCP tool receives it as a literal
string, so it does **not** resolve by default.

`create_step` bridges this: for a `/mnt/user-data/<rest>` virtual path, it
glob-searches the data root (`CAD_DATA_ROOT=/data`, mounted from
`backend/.deer-flow`) as `/data/users/*/threads/*/user-data/<rest>` (leaf =
new file, parent = searched) and uses the first match. A literal absolute
path also works. **Ceiling:** the glob assumes the thread dir is unique for
a given `<rest>`; upgrade path: carry `thread_id` via MCP context.

## Phase 1 limits (intentional)

- **One tool, STEP/STL only.** Inspection (measure/refs), snapshot (PNG/GIF
  review), assemblies, DXF 2D, URDF/SRDF/SDF, G-code slicing are later
  phases — clone more `@mcp.tool()` functions here (DXF can reuse
  `mcp-server/cad-mcp`'s analyze logic).
- **No snapshot/viewer.** deer-flow has no STEP viewer yet; the agent gets a
  downloadable STEP via `present_files`. A browser 3D viewer is a separate
  frontend task.
- **Agent authors source.** This container only executes build123d; the LLM
  (in the gateway) does the natural-language → source translation. That keeps
  the heavy runtime isolated and the reasoning where the context is.

## Skill-vs-MCP split (why not just install the text-to-cad skill?)

text-to-cad ships Claude-Code-style `SKILL.md` skills (format-compatible with
deer-flow). Two integration shapes:

- **Route A (this server):** capability as MCP tools — zero skill edits,
  gateway stays clean. Loses text-to-cad's workflow constraints (mandatory
  snapshot, assembly validation). Fastest to value.
- **Route B (skill + this server):** keep the `SKILL.md` in `skills/custom/`
  for the workflow (brief → model → inspect → snapshot → handoff), but
  rewrite its `python scripts/step` calls to invoke `text-to-cad_create_step`.
  Preserves the validation discipline; more work.

Route A is implemented here. Promote to Route B when the workflow constraints
matter.
