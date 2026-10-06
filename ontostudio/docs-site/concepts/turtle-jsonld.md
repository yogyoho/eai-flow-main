# Turtle 与 JSON-LD 1.1

> 对齐：`kernel/export.py` + 校验中心 C2 往返校验 @ 2026-10-06

## 一句话类比

**Turtle** 是图数据世界的 CSV——人可读、紧凑、一行行写三元组。**JSON-LD** 是"自带字段名翻译表的 JSON"——JSON 的皮，图的骨。同一个图，两种穿法。

## 在 OntoStudio 里对应什么

**Turtle**（`.ttl`）：图数据最通用的文本格式。三件套语法：

```turtle
@prefix dg: <http://ontostudio.example/dg#> .
dg:e123 a dg:graph_entity ;        # 分号 = 还是这个主语
    dg:label "西山遗址" ;           # 逗号后换属性行
    dg:etype "sensitive_point" .
```

`@prefix` 声明缩写；`;` 表示"主语不变，接着说"；`.` 结束一个陈述。人能直接读、直接 diff。

**JSON-LD 1.1**：给 JSON 加一个 `@context`（翻译表），把 `"etype"` 这样的短字段名映射回完整 IRI。REST API 友好——前端拿到的就是普通 JSON，但语义上等价于图。

**TriG**：Turtle 的超集，多一个"抽屉"概念（命名图）——一个文件装多个图，详见 [TriG 快照](./trig-snapshots)。

## 你在哪能看到/操作它

- **09 导出互操作**：一键导出 Turtle / JSON-LD，把当前图（schema 图 + 数据图）落成文件
- **C2 往返校验**（[国标符合性](../reference/gbt-48000#c2--条款-53--序列化往返)）：把 schema 图序列化成 Turtle 再装载回来，要求与原图**同构**——一个三元组都不能多、不能少。导出功能的正确性就是被这条校验兜住的
- 建模器保存后的 registry schema 图，底层同样以 Turtle 形态存在

## 常见坑

- **互转有语义边界**：Turtle → JSON-LD 无损；反向依赖 JSON-LD 1.1 的具名图支持（1.0 会丢图边界）。本系统导出以 Turtle 为正典。
- **别把 Turtle 当配置文件手编**：手编辑最容易破的是前缀（少个 `.`、拼错缩写），整个文件的解析就崩了。改 schema 走建模器，不走文本。
- **`a` 是保留速记**：Turtle 里 `x a y` 等价于 `x rdf:type y`——"x 是 y 类的实例"。读文件时别当成普通谓语。
