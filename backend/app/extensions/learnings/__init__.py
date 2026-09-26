"""learnings 扩展 — agent 自进化循环 P1(SQL 化捕获层).

EAI-CUSTOM: 设计 docs/designs/self-improving-loop-port.md(eng-review D1-D17)。

⚠️ gateway 不得 import 本包(零触碰约束): 表由 MCP 子进程
(`python -m app.extensions.learnings.mcp`)启动时 create_all; 子进程按需
lazy import 本包内模块。注册见 extensions_config.json mcpServers.learnings
(根 + deploy/offline 两份, cwd 必须为 null——D5/OV2 身份绑定前提)。
"""
