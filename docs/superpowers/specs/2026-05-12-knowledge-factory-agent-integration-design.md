# 知识工厂 ↔ Agent 双向协同集成设计

**日期**: 2026-05-12
**状态**: 草案
**作者**: 设计讨论

## 问题背景

知识工厂（Knowledge Factory）和 Agent 系统目前作为完全独立的模块运行。知识工厂拥有强大的知识提取、合规检查、法规库等能力，但 Agent 无法访问这些知识；反之，知识工厂用户也无法借助 Agent 的智能能力来辅助文档分析、规则生成、质量评估等工作。

## 目标

实现知识工厂与 Agent 系统的双向协同：

1. **Agent → 知识工厂**：Agent 通过 MCP Server 获得知识工具（法规搜索、模板查询、合规检查、质量评估等）
2. **知识工厂 → Agent**：知识工厂页面通过 Gateway API 调用 Agent 能力（AI 分析、AI 建议、AI 优化等）

## 架构设计

### 集成模式：MCP Server 桥接

```
┌─────────────────────────────────────────────────────────────┐
│                      前端 (Next.js)                          │
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
│                   网关 FastAPI (端口 8001)                     │
│                                                               │
│  /api/threads/{id}/runs/stream    /api/kf/*                  │
│           ↓                              ↓                    │
│  ┌────────────────┐    ┌─────────────────────────────────┐   │
│  │  RunManager     │    │   知识工厂服务层                  │   │
│  │  run_agent()    │    │   ├─ LawService（法规服务）      │   │
│  │       ↓         │    │   ├─ TemplateService（模板服务） │   │
│  │  Lead Agent     │    │   ├─ RuleService（规则服务）     │   │
│  │  (18 中间件)    │    │   ├─ QualityService（质量服务）  │   │
│  │       ↓         │    │   └─ DomainService（领域服务）   │   │
│  │  工具调用       │────│─→ MCP Server (kf_* 工具集)      │   │
│  │  kf_* tools     │    │                                 │   │
│  └────────────────┘    └─────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

### 为什么选择 MCP Server 桥接

| 评估维度 | MCP 桥接 | 直接 API 调用 | ACP 协议 |
|----------|---------|-------------|---------|
| 架构契合度 | 优秀（已有 MCP 机制） | 差（违反 harness/app 边界） | 过重（针对外部 Agent 设计） |
| 耦合程度 | 松耦合 | 紧耦合 | 松耦合 |
| 配置方式 | `extensions_config.json` 开关 | 硬编码 | `config.yaml` acp_agents |
| 双向支持 | 完整（第二阶段补充前端） | 完整 | 仅单向（方向2需额外方案） |
| 可发现性 | Agent 自动感知 | 手动注册 | 自动发现 |
| 可维护性 | 独立演进 | 交叉依赖 | 配置复杂 |

## 第一阶段：Agent → 知识工厂（MCP 工具）

### MCP Server：`knowledge-factory-server`

**类型**：Python stdio MCP Server
**位置**：`backend/app/extensions/knowledge_factory/mcp_server/`
**配置**：注册到 `extensions_config.json`

### 工具清单

| 工具名称 | 功能说明 | 依赖服务 | 参数 |
|---------|---------|---------|------|
| `kf_search_laws` | 按关键词、类别、领域搜索法规 | `LawService` | `query`（查询词）, `category?`（类别）, `domain?`（领域）, `limit?`（数量限制） |
| `kf_get_law_detail` | 获取法规全文及关联信息 | `LawService` | `law_id`（法规ID） |
| `kf_query_templates` | 按领域、状态、版本查询模板 | `TemplateService` | `domain_id?`（领域ID）, `status?`（状态）, `version?`（版本）, `limit?`（数量限制） |
| `kf_get_template` | 获取模板完整内容 | `TemplateService` | `template_id`（模板ID） |
| `kf_check_compliance` | 对内容执行合规检查 | `RuleService` | `content`（待检查内容）, `domain_id`（领域ID）, `rule_ids?`（指定规则ID列表） |
| `kf_evaluate_quality` | 评估模板质量评分 | `QualityService` | `template_id`（模板ID） |
| `kf_list_domains` | 列出可用的行业领域 | `DomainService` | `active_only?`（仅返回启用的领域） |
| `kf_search_rules` | 搜索合规规则 | `RuleService` | `query?`（查询词）, `domain_id?`（领域ID）, `rule_type?`（规则类型）, `limit?`（数量限制） |

### 实现细节

**服务入口**（`mcp_server/server.py`）：
- 使用 `mcp` Python SDK（`fastmcp` 或 `mcp` 包）
- Stdio 传输模式，通过进程间通信
- **数据库访问**：MCP Server 作为独立进程运行，使用与主应用相同的数据库 URL 创建独立的数据库会话。每次工具调用创建新会话、执行查询、然后关闭，避免与 Gateway 主进程的会话冲突

**工具实现模式**：
```python
@mcp.tool()
async def kf_search_laws(query: str, category: str | None = None, limit: int = 10) -> dict:
    """搜索法规库中的相关法规。"""
    results = await law_service.search(query=query, category=category, limit=limit)
    return {"laws": [law.to_summary_dict() for law in results]}
```

**配置**（`extensions_config.json`）：
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

### Agent 使用体验

用户在对话中提问时的交互示例：
- "帮我查一下大气污染防治相关的法规" → Agent 调用 `kf_search_laws(query="大气污染防治")`
- "这个模板的合规性如何？" → Agent 调用 `kf_check_compliance(content=..., domain_id=...)`
- "评估一下模板质量" → Agent 调用 `kf_evaluate_quality(template_id=...)`

## 第二阶段：知识工厂 → Agent（前端集成）

### AI 助手按钮

| 页面/组件 | AI 功能 | 触发方式 |
|-----------|--------|---------|
| 样本报告管理 | "AI 分析此文档" | 按钮 |
| 模板提取 | "AI 优化提取结果" | 按钮 |
| 模板编辑器 | "AI 改进模板" / "AI 检查完整性" | 侧边栏助手 |
| 法规库 | "AI 总结法规要点" / "AI 找相关法规" | 右键菜单/按钮 |
| 规则引擎 | "AI 生成规则建议" | 按钮 |
| 质量评估 | "AI 深度分析" | 按钮 |

### 实现机制

**线程管理**：
- 每个 AI 操作创建独立线程，附带元数据：`{source: "knowledge-factory", context: {page, entity_id, entity_type}}`
- 线程可复用——后续追问发送到同一线程
- 线程标题根据操作上下文自动生成

**提示词构建**：
- 前端组装结构化提示词，包含：
  - 操作类型（分析、优化、生成、检查）
  - 当前实体数据（模板内容、法规文本、规则定义）
  - 上下文信息（领域、关联实体）
  - 用户的具体请求或问题

**API 调用流程**：
```
1. POST /api/threads — 创建带元数据的线程
2. POST /api/threads/{id}/runs/stream — 启动 Agent 运行，传入结构化提示词
3. 前端订阅 SSE 流
4. 在对话框/侧边栏组件中渲染结果
5. 可选：回写至 /api/kf/* 以采纳 AI 建议
```

**前端组件架构**：
- 新组件：`KnowledgeFactoryAIAssistant`——可复用的对话框/侧边栏，展示 AI 结果
- 复用对话页面的 SSE 流式渲染组件
- 支持 Markdown + 结构化数据（表格、列表、代码块）渲染

### 结果回写

AI 建议可以回写到知识工厂：
- 用户在助手面板中审阅 AI 输出
- 点击"采纳"按钮将建议写回（如更新模板、创建规则）
- 回写操作使用现有的知识工厂 API 端点
- 审计追踪：回写操作记录 `source: ai-assistant` 标记

## 第三阶段：深度协同（远期规划）

### 上下文感知
- Agent 感知用户正在知识工厂中工作（通过线程元数据）
- Agent 主动推荐相关的知识工具
- 知识工厂操作出现在对话历史中

### 对话关联
- 知识工厂线程与主对话线程建立关联
- 用户可在对话中追问关于知识工厂 AI 操作的后续问题
- 聊天上下文与知识实体之间的交叉引用

### 批量操作
- Agent 可编排多步骤知识工厂工作流
- 示例："分析领域 X 的所有样本报告，提取共性模式，生成模板"

## 文件结构

```
backend/app/extensions/knowledge_factory/
├── mcp_server/                    # 新增 — 第一阶段
│   ├── __init__.py
│   ├── server.py                  # MCP 服务入口
│   └── tools/                     # 工具实现
│       ├── __init__.py
│       ├── law_tools.py           # kf_search_laws, kf_get_law_detail
│       ├── template_tools.py      # kf_query_templates, kf_get_template
│       ├── rule_tools.py          # kf_check_compliance, kf_search_rules
│       ├── quality_tools.py       # kf_evaluate_quality
│       └── domain_tools.py        # kf_list_domains
├── routers.py                     # 已有 — 添加 AI 助手端点
├── service.py                     # 已有
└── ...

frontend/src/extensions/knowledge-factory/
├── components/
│   ├── KnowledgeFactoryAIAssistant.tsx  # 新增 — 第二阶段
│   └── AIResultPanel.tsx               # 新增 — 第二阶段
├── hooks/
│   └── useAIAssistant.ts               # 新增 — 第二阶段
├── KnowledgeFactoryPage.tsx            # 修改 — 添加 AI 按钮
└── ...
```

## 测试策略

### 第一阶段测试
- 每个 MCP 工具的单元测试（mock 服务层）
- 集成测试：Agent → MCP 工具 → 服务层 → 数据库
- 端到端测试：用户提问 → Agent 调用 kf 工具 → 返回结果

### 第二阶段测试
- AIAssistant 组件测试
- 集成测试：按钮点击 → 线程创建 → SSE 流 → 结果渲染
- 端到端测试：知识工厂页面到 AI 结果的完整工作流

## 风险与应对

| 风险 | 可能性 | 影响程度 | 应对措施 |
|------|-------|---------|---------|
| MCP Server 启动失败 | 低 | 高 | Gateway 健康检查，降级错误提示 |
| 大量法规/模板数据超出 Agent 上下文窗口 | 中 | 中 | 实现结果摘要、分页机制 |
| 长时间 AI 操作期间 SSE 连接中断 | 中 | 低 | 通过 Last-Event-ID 重连，自动重试 |
| MCP 与服务层之间的数据库会话冲突 | 低 | 高 | 每次工具调用使用独立会话，确保会话生命周期管理 |
| 知识工厂数据访问权限控制 | 中 | 高 | 工具遵循 user_id 隔离，与现有服务保持一致 |
