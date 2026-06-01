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
- **Turbopack + transpilePackages breaks subpath exports:** Adding a package with pre-compiled `dist/` to `transpilePackages` in Next.js/Turbopack causes subpath imports like `@scope/pkg/locales` to resolve incorrectly. Turbopack tries source resolution and ignores the `exports` map, resulting in undefined imports at runtime. Only use `transpilePackages` for packages that actually need compilation (source with JSX/TS, no dist).
- **BlockNote AI dictionary:** The `@blocknote/xl-ai` AIExtension requires `editor.dictionary.ai` to be set. The dictionary must be merged with the base dictionary (`@blocknote/core/locales`): `{ ...coreEn, ai: aiEn }`. Using only `{ ai: aiEn }` replaces the entire base dictionary and loses core UI translations.
- **BlockNote lifecycle:** `useCreateBlockNote` manages editor lifecycle automatically. Do NOT call `editor.destroy()` manually in a useEffect cleanup.
- **BlockNote hooks API:** `useCreateBlockNote` accepts options as first arg and a deps array as second arg (like useMemo). The editor is recreated when deps change.
- **Hocuspocus 2.x hooks:** No `onDestroyDocument` — use `afterUnloadDocument({ documentName })` instead. The Document type from `@hocuspocus/server` has `connections` (Map) for checking active users.
- **Gateway vs Extensions user ID bridge:** The Hocuspocus collab server receives Gateway user IDs (from JWT sub) which differ from the Extensions PostgreSQL user IDs. The `bridgeGatewayUser()` function in persistence.ts calls Gateway API to get email, then looks up the extensions user by email.
- **BlockNote AI stream format:** The AI SDK's `DefaultChatTransport` expects SSE chunks with specific types. `{ type: "tool-call" }` is INVALID — use `{ type: "tool-input-start" }` followed by `{ type: "tool-input-available", toolCallId, toolName, input }`. The `@blocknote/xl-ai` AIExtension handles `tool-input-available` to apply tracked changes.
- **BlockNote AI menu review items:** The `@blocknote/xl-ai` AIMenu component does NOT have built-in accept/reject buttons. The `items` callback MUST return accept/reject items for "user-reviewing" status and retry/cancel items for "error" status. Call `ai.acceptChanges()` and `ai.rejectChanges()` from `editor.getExtension(AIExtension)`.

## Do-Not-Repeat

<!-- Mistakes made and corrected. Each entry prevents the same mistake recurring. -->
<!-- Format: [YYYY-MM-DD] Description of what went wrong and what to do instead. -->
- [2026-05-16] Never create a fresh SQLAlchemy engine per request in `get_db_context()` — it kills performance under even minimal load. Always reuse the shared engine pool.
- [2026-05-28] Do not try to import from `y-protocols/awareness` in frontend code — pnpm doesn't hoist it to top-level node_modules. Use `as any` cast for BlockNote's provider type instead.
- [2026-05-29] Do not add pre-compiled packages (like @blocknote/xl-ai) to `transpilePackages` in next.config.js — Turbopack's transpilePackages breaks subpath export resolution (e.g. `@scope/pkg/locales`), causing imports to resolve as `undefined` at runtime with no build-time error.
- [2026-05-30] `@blocknote/xl-ai/server` subpath import is broken in Turbopack — `aiDocumentFormats` resolves to `undefined`. Do not import from this path in Next.js API routes. Instead, implement the AI chat endpoint manually using direct `fetch()` to the LLM API with SSE stream forwarding.
- [2026-05-30] `@ai-sdk/openai` v2 defaults to the Responses API (`/v1/responses`). Use `openai.chat()` method to use the Chat Completions API. But even `openai.chat()` converts `system` role to `developer` role which non-OpenAI providers (DeepSeek, Zhipu) don't support. For non-OpenAI providers, bypass the AI SDK entirely and call the API directly.
- [2026-05-30] Next.js external rewrites (with full URL destinations) in `afterFiles` array intercept requests before API route handlers. Use `fallback` array for catch-all API rewrites so that local Next.js API routes take priority.
- [2026-05-30] Docker nginx `proxy_pass http://frontend` (no port) defaults to port 80, but Next.js container listens on port 3000. Always use explicit port: `deer-flow-frontend:3000`.
- [2026-05-30] Do NOT emit `{ type: "tool-call" }` in SSE stream for AI SDK's `DefaultChatTransport` — it triggers `AI_TypeValidationError`. The valid chunk types are `tool-input-start`, `tool-input-delta`, `tool-input-available`, `tool-output-available`, etc.
- [2026-05-30] The `@blocknote/xl-ai` AIMenu does NOT render built-in accept/reject buttons. You MUST return accept/reject items from the `items` callback when `status === "user-reviewing"`.

<!-- Mistakes made and corrected. Each entry prevents the same mistake recurring. -->
<!-- Format: [YYYY-MM-DD] Description of what went wrong and what to do instead. -->

## Decision Log

<!-- Significant technical decisions with rationale. Why X was chosen over Y. -->
- [2026-05-28] Chose BlockNote over Tiptap for the collab editor. BlockNote v0.51 provides native Yjs collaboration support (fragment + provider + user + showCursorLabels), Notion-style block editing, and built-in markdown import/export (blocksToMarkdownLossy, tryParseMarkdownToBlocks). The collaboration fragment key is "document-store" (not "thread").

- **Collab seeding flow:** When a document is first opened in the BlockNote collab editor, the Hocuspocus server's `onLoadDocument` loads from `collab_documents.yjs_doc`. If no entry exists, it sets `pendingMarkdown` in Yjs metadata (`_collabMeta`). The client's `BlockNoteEditor.tsx` reads this metadata, seeds from the markdown using `tryParseMarkdownToBlocks()`, then clears the flag. This ensures content is always seeded from the correct source (`ai_documents.content` or file_ref file content).
- **BlockNote `tryParseMarkdownToBlocks` limitations:** BlockNote's built-in markdown parser has limited support for complex markdown (tables, nested lists, mixed Chinese/English). For complex technical documents, the parsed blocks may differ from the original markdown structure.
- **Two-storage system pattern:** The collab system has two storage tables: `ai_documents.content` (original markdown) and `collab_documents.yjs_doc` (Yjs binary). They must be kept in sync through the seeding mechanism. Never use `blocksToMarkdownLossy()` to overwrite the original markdown from collab editor changes.
