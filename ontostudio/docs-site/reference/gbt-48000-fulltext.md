# GB/T 48000.3—2026 全文阅读

> 《标准数字化 第3部分：本体建模要求》，全国标准数字化标准化工作组（SAC/SWG29）归口，2026 发布。
> 版权归标准出版机构所有，本站托管仅供内部参考使用，请勿外传。
> 条款符合性落地情况见 [GB/T 48000.3 符合性校验（C1-C5）](./gbt-48000)。

## 全文阅读器

<iframe src="/ontostudio/docs/standards/GB-T-48000.3-2026.pdf" style="width:100%;height:820px;border:1px solid var(--vp-c-divider);border-radius:8px" title="GB/T 48000.3—2026 全文"></iframe>

*阅读器内可缩放/搜索/下载；或[新窗口打开 PDF](/ontostudio/docs/standards/GB-T-48000.3-2026.pdf)。*

## 章节地图

正文页码为标准自身页码；链接直达 PDF 对应页。

| 章节 | 正文页 | 直达 |
|---|---|---|
| 封面 / 目次 | — | [封面](/ontostudio/docs/standards/GB-T-48000.3-2026.pdf#page=1) · [目次](/ontostudio/docs/standards/GB-T-48000.3-2026.pdf#page=3) |
| 前言 / 引言 | Ⅲ / Ⅳ | [前言](/ontostudio/docs/standards/GB-T-48000.3-2026.pdf#page=5) · [引言](/ontostudio/docs/standards/GB-T-48000.3-2026.pdf#page=6) |
| 1 范围 / 2 规范性引用文件 / 3 术语和定义 | 1 | [直达](/ontostudio/docs/standards/GB-T-48000.3-2026.pdf#page=7) |
| 4 缩略语 | 2 | [直达](/ontostudio/docs/standards/GB-T-48000.3-2026.pdf#page=8) |
| **5 建模通用要求**（5.1 基本 / 5.2 核心组成 / 5.3 形式化 / 5.4 命名） | 2-3 | [直达](/ontostudio/docs/standards/GB-T-48000.3-2026.pdf#page=8) |
| **6 实体类型**（6.1 确定 / 6.2 核心实体类型 / 6.3 其他） | 3-8 | [6 章](/ontostudio/docs/standards/GB-T-48000.3-2026.pdf#page=9) · [6.2](/ontostudio/docs/standards/GB-T-48000.3-2026.pdf#page=10) |
| 7 实体类型属性（数据属性 / 对象属性） | 8-10 | [直达](/ontostudio/docs/standards/GB-T-48000.3-2026.pdf#page=14) |
| **8 本体公理与规则** | 10-11 | [直达](/ontostudio/docs/standards/GB-T-48000.3-2026.pdf#page=16) |
| **9 扩展方式和原则** | 11-12 | [直达](/ontostudio/docs/standards/GB-T-48000.3-2026.pdf#page=17) |
| 附录 A（规范性）实体类型及属性的元数据描述项 | 12-14 | [直达](/ontostudio/docs/standards/GB-T-48000.3-2026.pdf#page=18) |
| 附录 B（资料性）核心实体类型定义 | 14-20 | [直达](/ontostudio/docs/standards/GB-T-48000.3-2026.pdf#page=20) |
| 附录 C（资料性）数据属性定义（C.1-C.12） | 20-34 | [直达](/ontostudio/docs/standards/GB-T-48000.3-2026.pdf#page=26) |
| 附录 D（资料性）实例化示例 | 34-38 | [直达](/ontostudio/docs/standards/GB-T-48000.3-2026.pdf#page=40) |
| 参考文献 | 38 | [直达](/ontostudio/docs/standards/GB-T-48000.3-2026.pdf#page=44) |

## 与本系统符合性的映射

| 国标条款 | 本系统落地 | 证据页 |
|---|---|---|
| 5.4 命名方式 | C1：域命名空间 http(s) 形态 + 实例 IRI=`ns+id/<uuid>` 机械可逆 | [C1-C5 符合性](./gbt-48000#c1--条款-54--iri-命名规约) |
| 5.3 形式化要求 | C2 序列化往返（Turtle round-trip）+ C3 SHACL 报告五要素 | [C2](./gbt-48000#c2--条款-53--序列化往返) · [C3](./gbt-48000#c3--条款-53--shacl-报告) |
| 附录 A 元数据描述项 | C4：类声明/标签齐备，subClassOf 目标已声明 | [C4](./gbt-48000#c4--附录-a--元数据八项) |
| 9 扩展方式和原则 | C5：域命名空间唯一非 W3C 保留，类名合法 | [C5](./gbt-48000#c5--条款-9--扩展原则) |
| 6.2 核心实体类型 | 法规域建模的目录骨架参考（标准实体/标准化对象/相关方/要素/层次/约束逻辑等分类） | [本体地基](../concepts/foundations) |
| 8 本体公理与规则 | 本系统以 owlrl 标准规则 + CONSTRUCT 业务规则实现推理；**公理级形式化建模当前为空**（诚实边界） | [双层推理](../concepts/sparql-construct) · [边界与规划](./gbt-48000#边界与规划-诚实声明) |
