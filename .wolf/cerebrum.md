# Cerebrum

> OpenWolf's learning memory. Updated automatically as the AI learns from interactions.
> Do not edit manually unless correcting an error.
> Last updated: 2026-05-11

## User Preferences

<!-- How the user likes things done. Code style, tools, patterns, communication. -->

## Key Learnings

- **Project:** eai-flow-main
- **Description:** English | [中文](./README_zh.md) | [日本語](./README_ja.md) | [Français](./README_fr.md) | [Русский](./README_ru.md)
- **Database session providers:** Always reuse a shared engine pool. Never create+dispose engines per request — the overhead is catastrophic. Use `pool_pre_ping=True` instead of `SELECT 1` validation on every request.
- **Nginx upstream keepalive:** Always add `keepalive N` to upstream blocks and set `proxy_set_header Connection ''` on location blocks to reuse TCP connections to backend.
- **MCP skill tool filtering:** Skills with `allowed-tools` declarations in SKILL.md cause `filter_tools_by_skill_allowed_tools()` to strip ALL tools not in the allowed list, including MCP tools. If no skills are enabled, the filter returns None (allow-all). Disabled/renamed skills don't count.
- **MCP lazy init + caching:** `get_cached_mcp_tools()` caches MCP tools after first successful initialization. The cache invalidates on `extensions_config.json` mtime changes. First agent run may have empty MCP tools if init hasn't completed yet.
- **MCP Word server path issue:** Office-Word-MCP-Server's `create_document` saves files relative to the MCP server's CWD (which is `/app/backend/` in Docker), NOT the container's virtual path system (`/mnt/user-data/outputs/`). The agent cannot directly place files into the virtual path system via MCP tools.
- **Docker container names:** This project uses `docker compose -p eai-docker`, so containers are named `eai-docker-*` (but actual names are `deer-flow-gateway`, `deer-flow-frontend`, `deer-flow-nginx`). Always `docker ps` to verify.
- **Admin email:** The admin account in the Docker DB is `admin@eai-flow.com` (not `admin@eai.local`).
- **BlockNote provider type cast:** HocuspocusProvider has `awareness: Awareness | null` but BlockNote's `CollaborationOptions.provider` expects `{ awareness?: Awareness }`. Since `y-protocols/awareness` is not hoisted to top-level node_modules, use `provider as any` cast to bridge the types.
- **BlockNote CSS imports:** BlockNote requires two CSS files: `@blocknote/shadcn/dist/style.css` and `@blocknote/react/dist/style.css`. The CSS files are only in `dist/`, not at the package root.
- **BlockNote lifecycle:** `useCreateBlockNote` manages editor lifecycle automatically. Do NOT call `editor.destroy()` manually in a useEffect cleanup.
- **BlockNote hooks API:** `useCreateBlockNote` accepts options as first arg and a deps array as second arg (like useMemo). The editor is recreated when deps change.

## Do-Not-Repeat

<!-- Mistakes made and corrected. Each entry prevents the same mistake recurring. -->
<!-- Format: [YYYY-MM-DD] Description of what went wrong and what to do instead. -->
- [2026-05-16] Never create a fresh SQLAlchemy engine per request in `get_db_context()` — it kills performance under even minimal load. Always reuse the shared engine pool.
- [2026-05-28] Do not try to import from `y-protocols/awareness` in frontend code — pnpm doesn't hoist it to top-level node_modules. Use `as any` cast for BlockNote's provider type instead.

<!-- Mistakes made and corrected. Each entry prevents the same mistake recurring. -->
<!-- Format: [YYYY-MM-DD] Description of what went wrong and what to do instead. -->

## Decision Log

<!-- Significant technical decisions with rationale. Why X was chosen over Y. -->
- [2026-05-28] Chose BlockNote over Tiptap for the collab editor. BlockNote v0.51 provides native Yjs collaboration support (fragment + provider + user + showCursorLabels), Notion-style block editing, and built-in markdown import/export (blocksToMarkdownLossy, tryParseMarkdownToBlocks). The collaboration fragment key is "document-store" (not "thread").
