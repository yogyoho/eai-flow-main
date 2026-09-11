# tech_outline_packs——技术卷大纲骨架包(16 类, 已填充 2026-09-11)

用途(spec §3.3): 技术卷 TOC 自拟的分类骨架层——分类器判定项目类别 → 装载 `<类别>.json`
→ 招标技术要求/评分办法按评分项关键词聚类实例化 → 对话确认门。依据调研:
docs/designs/bid-tech-outline-packs-research.md。

## 16 类登记(状态=待填充; 文件名=本表 slug)

| slug | 类别 | 调研 confidence | 状态 |
|---|---|---|---|
| engineering | 工程类(施工总承包主骨架) | 9/10 | 已填充 |
| goods | 货物类(设备/物资采购主骨架) | 7/10 | 已填充 |
| services | 服务类(勘察/设计/监理/咨询主骨架) | 8/10 | 已填充 |
| it-platform | 信息系统/软件平台类(主骨架) | 7/10 | 已填充 |
| construction | 工程施工类(房建/市政施组) | 9/10 | 已填充 |
| epc | EPC 工程总承包类 | 7/10 | 已填充 |
| design | 工程设计类 | 8/10 | 已填充 |
| goods-general | 通用供货类 | 8/10 | 已填充 |
| goods-medical | 医疗设备采购类 | 7/10 | 已填充 |
| goods-heavy | 大型机械装备/成套设备类 | 7/10 | 已填充 |
| it-full | IT 软件平台与系统集成(详版·方案型) | 9/10 | 已填充 |
| it-lite | IT 信息化(简版·响应型) | 7/10 | 已填充 |
| it-ops | IT 运维服务类 | 9/10 | 已填充 |
| supervision | 工程监理服务类 | 8/10 | 已填充 |
| consulting | 咨询服务类 | 7/10 | 已填充 |
| inspection | 检验检测服务类 | 6/10 | 已填充 |

## pack 文件形态(填充时遵守)

`<slug>.json`: `{"slug": …, "类别": …, "aliases": […], "chapters": [{"no": 1, "title": …,
"notes": …}], "source": "调研文档节名"}`——章纲=调研文档对应表逐行; 填充后在本表状态列
改"已填充"。骨架是**大纲候选素材**, 不直接写盘 state(见 SKILL.md B1 v1 边界)。
