# Engineering Drawing Platform Spec

文本 → 2D 工程图生成平台。领域无关核心 composer + 可插拔 domain pack。
首个领域:煤矿设计图;验证领域:化工厂 P&ID。`cad-mcp`(8003,ezdxf+matplotlib)承载。

> 决策记录见 `.wolf/cerebrum.md` Decision Log [2026-06-24]。
> 单向门已锁:① 符号 = 声明式 JSON spec(非 DXF block);② pack = 容器内 `domains/<domain>/`(非独立仓库)。

## 1. 架构

```
Skill 层       mine-design skill │ chemplant-design skill │ ...
─────────────────────────────────────────────────────────────
domain pack    domains/mine/            domains/chem/         (声明式资产)
─────────────────────────────────────────────────────────────
核心 composer  compose_drawing(domain, drawing_type, intent_json)
  registry → 查 pack.drawing_types[drawing_type] 得 strategy
           → load pack.symbols (type → SymbolSpec)
           → strategy.render(msp, entities, symbols, frame, layers)
           → 套图框 → 校验 → matplotlib 栅格预览
```

核心**不知道**巷道/泵的存在,只认:`entity.type → SymbolSpec`、`entity.placement.kind → 策略`。
新增范式 = 新 `placement.kind` + 新 RenderStrategy,核心不动。

## 2. 符号 JSON spec 格式(已定:声明式)

`domains/<domain>/symbols/<type>.json`。符号 = 基元(op)列表 + 锚点 + 端口(schematic 用)+ 标签锚。

```jsonc
{
  "type": "pump",
  "domain": "chem",
  "insertion_base": [0, 0],
  "default_size_mm": 500,
  "default_layer": "设备",
  "primitives": [
    {"op": "circle", "cx": 0, "cy": 0, "r": 250},
    {"op": "polyline", "points": [[-250, 0], [-400, 0]]},
    {"op": "text", "x": 0, "y": -350, "string": "P", "height": 80}
  ],
  "ports": [{"id": "in", "at": [-400, 0]}, {"id": "out", "at": [400, 0]}],
  "label_anchor": [0, 350]
}
```

### 基元词汇表(op)— 核心契约,所有 domain pack 共用

| op | 字段 | 备注 |
|---|---|---|
| `line` | x1,y1,x2,y2 | |
| `polyline` | points[], closed? | lwpolyline |
| `circle` | cx,cy,r | |
| `arc` | cx,cy,r,start_angle,end_angle | 度 |
| `text` | x,y,string,height,rotation? | |
| `hatch` | boundary(points[]), pattern | 填充(支护喷浆/煤层/采空区) |
| `insert` | type, at, scale?, rotate? | 嵌套符号,组合复用 |

不认得的 op → 校验报错(不静默画空)。`ports` 仅 schematic 策略消费(layout 符号留空)。
复杂到 JSON 表达不了的符号 → 留逃生舱(后续支持 `external_dxf` op 引用块文件),但 MVP 不做。

## 3. 实体意图 schema

LLM(skill 层)产出,composer 消费。一个 `entities[]` 服务所有范式。

```jsonc
{
  "domain": "mine",
  "drawing_type": "roadway_section",
  "frame": {"standard": "GB14689", "size": "A3", "scale": "1:50", "north": 0},
  "layers": [{"name": "巷道", "color": 3}],
  "entities": [
    {"id": "rd-1", "type": "roadway", "layer": "巷道",
     "placement": {"kind": "polyline", "coords": [[0,0],[4000,0]], "width_mm": 4000},
     "attrs": {"name": "主运巷"}}
  ],
  "annotations": [
    {"kind": "dimension", "from": [0,0], "to": [4000,0], "value_mm": 4000},
    {"kind": "elevation", "at": [2000,2500], "value_m": -450.0}
  ],
  "title_block": {"mine": "XX煤矿", "level": "-450", "drawing_name": "主运巷断面图", "date": "2026-06"}
}
```

### placement.kind 词汇表(核心契约)

| kind | 范式 | 字段 | 渲染器行为 |
|---|---|---|---|
| `point` | layout | at, rotate?, scale? | 在坐标放符号块(钻孔/风门/设备) |
| `polyline` | layout | coords[], width? | 有 width→偏移双线(巷道/管道);无→单线 |
| `region` | layout | coords[](闭合) | 闭合多段线 + 可选 hatch(采空区/煤层边界) |
| `node` | schematic | at, rotate? | 放带 ports 的符号 |
| `edge` | schematic | from, to, route, waypoints? | 在 port 间布线(auto/ortho/manual) |
| `iso_segment` | isometric(未来) | — | 管段图,后置 |

`from`/`to` = `{"node":"V-1","port":"out"}` 或裸坐标。`route` ∈ `auto|ortho|manual`。

### annotations(领域无关,通用渲染器)

| kind | 字段 |
|---|---|
| `dimension` | from[], to[], value_mm?, label? |
| `leader_text` | at[], text |
| `elevation` | at[], value_m |
| `coord_label` | at[], value |
| `text` | at[], string, height |

## 4. pack 目录布局(已定:容器内 `domains/`)

```
mcp-server/cad-mcp/
  server.py                      # compose_drawing 工具(新增)+ analyze_cad(保留)
  edp/                           # engineering-drawing-platform 核心
    registry.py                  # load pack by domain
    composer.py                  # 调度: pack→strategy→symbols→render→frame→validate→raster
    strategies/
      layout.py                  # layout RenderStrategy
      schematic.py               # schematic RenderStrategy(chem P&ID)
    frame.py  layers.py  annotate.py  validate.py  raster.py
  domains/
    mine/
      manifest.json
      symbols/  roadway.json  borehole.json  airdoor.json  fault.json ...
      frame_templates/  gb14689_a3.json ...
    chem/
      manifest.json
      symbols/  vessel.json  pump.json  valve.json  pipe.json  instrument.json ...
```

### pack manifest(`domains/<domain>/manifest.json`)

```jsonc
{
  "domain": "mine",
  "drawing_types": {
    "roadway_section": {"strategy": "layout",    "frame": "GB14689-A3", "scale_default": "1:50"},
    "mining_plan":     {"strategy": "layout",    "frame": "GB14689-A1", "scale_default": "1:2000", "coord_grid": true},
    "ventilation":     {"strategy": "layout",    "frame": "GB14689-A2"}
  },
  "symbols_glob": "symbols/*.json",
  "layers": {"巷道": {"color": 3}, "通风": {"color": 5}, "地质": {"color": 6}},
  "rules": "rules.py"
}
```

`drawing_type` 声明用哪个 strategy + 默认图框/比例 → `compose_drawing` 不收 strategy 参数。
`rules.py`(可选)暴露 domain 专属钩子(MVP 不强制)。

## 5. RenderStrategy 契约

```python
class RenderStrategy(Protocol):
    name: str  # "layout" | "schematic" | "isometric"
    def render(self, msp, entities: list[Entity], symbols: SymbolLib,
               frame: Frame, layers: LayerSet) -> RenderReport: ...
```

- 按 `entity.placement.kind` 各取所需;不认得的 kind → 计入 `RenderReport.skipped`,不崩。
- `symbols.resolve(type) → SymbolSpec`;未知 type → skip + report。
- 输出 `RenderReport{placed:int, skipped:[{id,reason}], bounds_mm}` 供校验与栅格。

## 6. compose_drawing 工具 API(扩 cad-mcp)

```
compose_drawing(domain, drawing_type, intent_json, output_path, also_png=True)
  domain:        "mine" | "chem" | ...
  drawing_type:  pack manifest 里声明的图种
  intent_json:   第 3 节 schema 的意图对象
  output_path:   .dxf 绝对路径或 /mnt/user-data/outputs/<name>.dxf
  also_png:      同时栅格预览(cad-mcp 已有 matplotlib 能力)
→ {status:"ok", dxf, png?, report:{placed, skipped[], validations[]}}
→ {status:"error", error, detail?}
  error ∈ unknown_domain | unknown_drawing_type | schema_invalid | render_failed | resolve_failed | bad_suffix
```

agent 侧工具名:`cad_compose_drawing`(`tool_name_prefix=True`)。

## 7. 符号清单(MVP 范围,自建,按 MT/HG 标准定义 op)

**mine MVP(roadway_section,layout):** roadway(polyline,双线)、support 锚喷(hatch)、
dimension/elevation(走通用 annotation)。最小符号集 ~3 类。

**mine 第二批(验证扩展):** borehole(⊙+孔号)、airdoor、airflow_arrow、fault、coal_seam(region hatch)。

**chem MVP(pid 片段,schematic):** vessel(node,带 ports)、pump(node,带 ports)、valve(node)、
pipe(edge,auto route)、instrument(圆圈+位号)。~5 类。HG/T 20519 / ISO 10628。

## 8. 构建顺序 + MVP 验收

1. **核心**:registry + composer 调度 + layout 策略 + frame/layers/annotate/validate/raster。
2. **mine pack**:roadway_section + 最小符号 → **验收 M1**:文本/尺寸表 → roadway_section DXF,
   体积无意义,改校验:实体数、图层齐、图框在、标注非空、所有 type 解析、坐标范围合理 + PNG 预览。
3. **chem pack + schematic 策略**:最简 P&ID(vessel→pipe→pump)→ **验收 M2(平台成立判据)**:
   node 符号 ports 正确、edge 在 port 间路由、schematic 策略与 layout 策略共存于同一核心。
   M2 跑通 = 抽象没漏,平台成立。
4. 扩 mine 第二批符号;加 mining_plan 的 coord_grid;isometric 策略(管段图)后置。

**验收硬线**:每张图必须过 `validate`(实体数/图层/图框/标注/符号解析/坐标范围)并产出 PNG,
只报告**实际跑过**的检查(沿用 cad-modeling 的诚实纪律,不虚报)。

## 9. 后置(不在 MVP)

- isometric 策略(化工管段图)。
- mining_plan 的真实测绘坐标 + 方格网分幅 + 多图幅拼接。
- pack 分发升级(独立仓库 / plugin),等 2+ 领域有分发压力再做。
- 符号 `external_dxf` 逃生舱(JSON 表达不了的复杂符号)。
- 前端 DXF/PNG 在线预览(cad-mcp 已能产 PNG,前端 viewer 后置)。
