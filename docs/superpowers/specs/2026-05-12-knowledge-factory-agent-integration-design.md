# Knowledge Factory ↔ Agent Bidirectional Integration Design

**Date**: 2026-05-12
**Status**: Draft
**Author**: Design session

## Problem

The Knowledge Factory (知识工厂) and the Agent system operate as completely independent modules. Knowledge Factory provides powerful extraction, compliance checking, and law library capabilities, but the Agent cannot access any of this knowledge. Conversely, knowledge factory users cannot leverage the Agent's intelligence to assist with tasks like document analysis, rule generation, or quality evaluation.

## Goal

Enable bidirectional coordination between the Knowledge Factory and the Agent system:

1. **Agent → Knowledge Factory**: Agent gains knowledge tools (law search, template query, compliance check, quality evaluation) via MCP Server
2. **Knowledge Factory → Agent**: Knowledge Factory pages can invoke Agent capabilities (AI analysis, AI suggestions, AI optimization) via Gateway API

## Architecture

### Integration Pattern: MCP Server Bridge

```
┌─────────────────────────────────────────────────────────────┐
│                      Frontend (Next.js)                      │
│                                                              │
│  ┌──────────────────┐          ┌──────────────────────────┐ │
│  │   对话页面        │          │   知识工厂页面             │ │
│  │                  │          │                          │ │
│  │  用户输入        │          │  [AI 分析] [AI 检查]     │ │
│  │  Agent 回复      │          │  [AI 优化] [AI 生成]     │ │
│  │  (含知识工厂数据) │          │       ↓                  │ │
│  └───────┬──────────┘          │  SSE 结果渲染            │ │
│          │                     └──────────┬───────────────┘ │
└──────────┼────────────────────────────────┼─────────────────┘
           │                                │
           ↓                                ↓
┌──────────────────────────────────────────────────────────────┐
│                   Gateway FastAPI (port 8001)                 │
│                                                               │
│  /api/threads/{id}/runs/stream    /api/kf/*                  │
│           ↓                              ↓                    │
│  ┌────────────────┐    ┌─────────────────────────────────┐   │
│  │  RunManager     │    │   知识工厂 Services              │   │
│  │  run_agent()    │    │   ├─ LawService                 │   │
│  │       ↓         │    │   ├─ TemplateService            │   │
│  │  Lead Agent     │    │   ├─ RuleService                │   │
│  │  (18 中间件)    │    │   ├─ QualityService             │   │
│  │       ↓         │    │   └─ DomainService              │   │
│  │  工具调用       │────│─→ MCP Server (kf_* tools)       │   │
│  │  kf_* tools     │    │                                 │   │
│  └────────────────┘    └─────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

### Why MCP Server Bridge

| Criteria | MCP Bridge | Direct API | ACP Protocol |
|----------|-----------|------------|--------------|
| Architecture fit | Excellent (existing MCP mechanism) | Poor (violates harness/app boundary) | Overkill for internal module |
| Coupling | Loose | Tight | Loose |
| Configuration | `extensions_config.json` toggle | Hardcoded | `config.yaml` acp_agents |
| Bidirectional | Yes (Phase 2 adds frontend) | Yes | No (direction 2 needs extra) |
| Discoverability | Auto-visible to Agent | Manual registration | Auto via ACP |
| Maintenance | Independent evolution | Cross-dependency | Complex |

## Phase 1: Agent → Knowledge Factory (MCP Tools)

### MCP Server: `knowledge-factory-server`

**Type**: Python stdio MCP Server
**Location**: `backend/app/extensions/knowledge_factory/mcp_server/`
**Configuration**: Registered in `extensions_config.json`

### Tool Catalog

| Tool Name | Description | Service Used | Parameters |
|-----------|-------------|-------------|------------|
| `kf_search_laws` | Search laws by keyword, category, or domain | `LawService` | `query`, `category?`, `domain?`, `limit?` |
| `kf_get_law_detail` | Get full law text and related info | `LawService` | `law_id` |
| `kf_query_templates` | Query templates by domain, status, version | `TemplateService` | `domain_id?`, `status?`, `version?`, `limit?` |
| `kf_get_template` | Get template full content | `TemplateService` | `template_id` |
| `kf_check_compliance` | Run compliance check on content | `RuleService` | `content`, `domain_id`, `rule_ids?` |
| `kf_evaluate_quality` | Evaluate template quality score | `QualityService` | `template_id` |
| `kf_list_domains` | List available industry domains | `DomainService` | `active_only?` |
| `kf_search_rules` | Search compliance rules | `RuleService` | `query?`, `domain_id?`, `rule_type?`, `limit?` |

### Implementation Details

**Server entry point** (`mcp_server/server.py`):
- Uses `mcp` Python SDK (`fastmcp` or `mcp` package)
- Stdio transport for process-based communication
- **Database access**: MCP server runs as a separate process. It creates its own database sessions using the same database URL as the main application. Each tool call creates a new session, executes the query, and closes it. This avoids session conflicts with the main Gateway process while sharing the same data layer

**Tool implementation pattern**:
```python
@mcp.tool()
async def kf_search_laws(query: str, category: str | None = None, limit: int = 10) -> dict:
    """Search the law library for relevant regulations."""
    results = await law_service.search(query=query, category=category, limit=limit)
    return {"laws": [law.to_summary_dict() for law in results]}
```

**Configuration** (`extensions_config.json`):
```json
{
  "mcpServers": {
    "knowledge-factory": {
      "enabled": true,
      "type": "stdio",
      "command": "python",
      "args": ["-m", "app.extensions.knowledge_factory.mcp_server"],
      "env": {}
    }
  }
}
```

**Database access**: MCP server runs as a separate stdio process. Each tool creates its own database session (same DB URL as Gateway) and closes it after use. This ensures clean session lifecycle and no conflicts with the main process.

### Agent Experience

When a user asks in the chat:
- "帮我查一下大气污染防治相关的法规" → Agent calls `kf_search_laws(query="大气污染防治")`
- "这个模板的合规性如何？" → Agent calls `kf_check_compliance(content=..., domain_id=...)`
- "评估一下模板质量" → Agent calls `kf_evaluate_quality(template_id=...)`

## Phase 2: Knowledge Factory → Agent (Frontend Integration)

### AI Assistant Buttons

| Page/Component | AI Feature | Trigger |
|----------------|-----------|---------|
| Sample Reports | "AI 分析此文档" | Button |
| Template Extraction | "AI 优化提取结果" | Button |
| Template Editor | "AI 改进模板" / "AI 检查完整性" | Sidebar assistant |
| Law Library | "AI 总结法规要点" / "AI 找相关法规" | Context menu / Button |
| Rule Engine | "AI 生成规则建议" | Button |
| Quality Evaluation | "AI 深度分析" | Button |

### Implementation Mechanism

**Thread management**:
- Each AI operation creates a dedicated thread with metadata: `{source: "knowledge-factory", context: {page, entity_id, entity_type}}`
- Threads are reusable — follow-up questions go to the same thread
- Thread title auto-generated based on operation context

**Prompt construction**:
- Frontend builds a structured prompt containing:
  - Operation type (analyze, optimize, generate, check)
  - Current entity data (template content, law text, rule definition)
  - Context (domain, related entities)
  - User's specific request or question

**API flow**:
```
1. POST /api/threads — create thread with metadata
2. POST /api/threads/{id}/runs/stream — start agent run with structured prompt
3. Frontend subscribes to SSE stream
4. Render results in dialog/sidebar component
5. Optionally: POST back to /api/kf/* to apply AI suggestions
```

**Frontend component architecture**:
- New component: `KnowledgeFactoryAIAssistant` — reusable dialog/sidebar for AI results
- Uses existing SSE streaming components from the chat page
- Renders Markdown + structured data (tables, lists, code blocks)

### Result Write-back

AI suggestions can be applied back to Knowledge Factory:
- User reviews AI output in the assistant panel
- "Adopt" button writes the suggestion back (e.g., update template, create rule)
- Write-back uses existing Knowledge Factory API endpoints
- Audit trail: write-back operations logged with `source: ai-assistant`

## Phase 3: Deep Coordination (Future)

### Context Awareness
- Agent knows when user is working in Knowledge Factory (via thread metadata)
- Agent proactively suggests relevant knowledge tools
- Knowledge Factory operations appear in conversation history

### Conversation Linkage
- Knowledge Factory threads linked to main conversation threads
- User can ask follow-up questions in the chat about a Knowledge Factory AI operation
- Cross-reference between chat context and knowledge entities

### Batch Operations
- Agent can orchestrate multi-step knowledge factory workflows
- Example: "Analyze all sample reports in domain X, extract common patterns, and generate a template"

## File Structure

```
backend/app/extensions/knowledge_factory/
├── mcp_server/                    # NEW — Phase 1
│   ├── __init__.py
│   ├── server.py                  # MCP server entry point
│   └── tools/                     # Tool implementations
│       ├── __init__.py
│       ├── law_tools.py           # kf_search_laws, kf_get_law_detail
│       ├── template_tools.py      # kf_query_templates, kf_get_template
│       ├── rule_tools.py          # kf_check_compliance, kf_search_rules
│       ├── quality_tools.py       # kf_evaluate_quality
│       └── domain_tools.py        # kf_list_domains
├── routers.py                     # Existing — add AI assistant endpoints
├── service.py                     # Existing
└── ...

frontend/src/extensions/knowledge-factory/
├── components/
│   ├── KnowledgeFactoryAIAssistant.tsx  # NEW — Phase 2
│   └── AIResultPanel.tsx               # NEW — Phase 2
├── hooks/
│   └── useAIAssistant.ts               # NEW — Phase 2
├── KnowledgeFactoryPage.tsx            # Modified — add AI buttons
└── ...
```

## Testing Strategy

### Phase 1 Tests
- Unit tests for each MCP tool (mock services)
- Integration test: Agent → MCP tool → service → database
- E2E test: User asks question → Agent calls kf tool → returns result

### Phase 2 Tests
- Component tests for AIAssistant
- Integration test: Button click → thread creation → SSE stream → result render
- E2E test: Full workflow from knowledge factory page to AI result

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| MCP server startup failure | Low | High | Health check in Gateway, fallback error message |
| Large law/template data overwhelming Agent context | Medium | Medium | Implement result summarization, pagination |
| SSE connection drops during long AI operations | Medium | Low | Reconnect with Last-Event-ID, retry logic |
| Database session conflicts between MCP and services | Low | High | Use separate session per tool call, proper session lifecycle |
| Knowledge Factory data access control | Medium | High | Tools respect user_id scoping, same as existing services |
