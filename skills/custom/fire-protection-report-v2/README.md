# Fire Protection Report Skill v2

## 与 v1 的区别

v2 核心改进：

| 维度 | v1 | v2 |
|------|----|----|
| 状态 | 已废弃，指向 v2 | 当前维护版本 |
| 数据源 | 纯 markdown 静态文件 | 模板优先 + markdown fallback |
| 章节生成 | 通用 prompt | 每章独立 generation_hint |
| 内容约束 | 隐式 | 显式 content_contract（字数/结构/禁用词/要素） |
| 合规规则 | 全局 GB 列表 | 每章独立 compliance_rules |
| 模板演进 | 改文件 | 知识工厂编辑模板 → 即时生效 |
| 输出方式 | word-document-server MCP 直接生成 .docx | 结构化 Markdown 写入 outputs → present_files 自动同步文档空间（用户编辑排版后导出 Word） |

## 目录结构

```
fire-protection-report-v2/
├── SKILL.md                    # 技能定义（模板优先工作流）
├── references/
│   ├── report_structure.md     # 8章结构（fallback）
│   ├── terminology.md          # 术语词典（始终加载）
│   ├── content_guidelines.md   # 编写指南（始终加载）
│   └── chapter_examples/
│       └── sample_fire_design.md
└── README.md
```

## 触发方式

- "生成消防设计专篇"
- "编写消防设计报告"
- "创建消防设计专篇"
- "化工项目消防设计"
- "消防设计说明书"
- "消防验收报告"
- "消防设计审查"
- "防火设计专篇"

## 依赖

- `knowledge-factory_kf_resolve_template`（knowledge-factory MCP Server）— 模板匹配
- `present_files` 回调（无独立 docmgr MCP）— 写入 outputs 后自动同步为文档空间 AIDocument
- 无需 word-document-server MCP — 用户在文档空间编辑排版后自行导出 Word
