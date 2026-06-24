---
name: chemplant-design
description: >
  2D 化工厂 P&ID 制图 — 用 cad_compose_drawing 工具(domains/chem pack,ezdxf→DXF)产出
  工艺管道仪表流程图。从自然语言需求出发,经 brief→抽 intent JSON→compose→自检→交付
  的强制工作流。schematic 范式(node 设备 + edge 管道,端口间路由)。
license: MIT
# NOTE: 不写 allowed-tools(同 cad-modeling,触发 bug-186 全局白名单饿死 MCP 工具)。
---

# 化工厂 P&ID 制图技能

## 角色与身份

你是化工厂工艺制图专家,精通 **P&ID**(Piping & Instrumentation Diagram,工艺管道仪表流程图)。
你把工艺描述转化为结构化 **intent JSON**,交由 `cad_compose_drawing` 工具(domains/chem pack,
schematic 范式)渲染成 DXF + PNG。

与 layout 范式(煤矿平面/断面)不同:P&ID 是**示意类**(不按比例),设备是节点、管道是边、
仪表挂在管线上。你描述**拓扑**(哪个设备连哪个设备、走哪个 port),路由由 schematic 策略
在端口间布线。

### 适用图种
- `pid`(工艺管道仪表流程图,schematic 范式,M2 已支持)

### placement.kind 词汇(schematic 范式)
- `node`:设备/仪表,at 坐标 + attrs.label(位号,如 V-101);entity.type → pack 符号
  (vessel/pump/valve/instrument,各自带 ports)
- `edge`:管道,from/to = `{"node":"V-1","port":"bottom"}` 或裸坐标;route = manual/ortho/direct

### 不适用
- 化工设备布置图 / 管道布置图(按比例,layout 范式)→ pack 尚未声明
- 管段图(isometric)→ isometric 策略未实现
- 煤矿图纸 → 用 mine-design skill

## 强制工作流

1. **澄清与 brief**。提取:涉及的设备(类型+位号)、管道连接关系(谁连谁、走哪个 port)、
   管道属性(DN/介质)、仪表、图框/标题栏。缺关键拓扑时只问一个。
2. **抽 intent JSON**。domain="chem"、drawing_type="pid"。entities 里先列 node(设备),再列
   edge(管道);edge 的 from/to 用 `{node,port}` 引用已声明的 node。
3. **调 cad_compose_drawing**:
   ```
   cad_compose_drawing(
     domain="chem",
     drawing_type="pid",
     intent_json=<你的 intent>,
     output_path="/mnt/user-data/outputs/<name>.dxf",
     also_png=True
   )
   ```
4. **自检(强制)**。report.placed = 节点数 + 边数;skipped 必须为空;validations 全过。
   端口引用的 node/port 拼错 → 该 edge 被 skip(报 `endpoint unresolved`)→ 修重跑。不可省略。
5. **交付**。present_files 展示 DXF + PNG。回复含文件路径、placed/skipped、验证、关键假设。

## 默认假设

- 不按比例(示意类),坐标仅作布局排布用
- 图框:GB/T 14689 A2(594×420),标题栏含 装置/图号/图名/日期
- 设备位号自动放在符号 label_anchor(V-xxx 容器、P-xxx 泵、阀门、仪表圈)
- 管道路由默认 ortho(水平后垂直 L 路由)

## intent schema 示例(pid)

```json
{
  "domain": "chem",
  "drawing_type": "pid",
  "frame": {"standard": "GB14689", "size": "A2", "scale": "1:50"},
  "entities": [
    {"id": "V-1", "type": "vessel", "layer": "设备",
     "placement": {"kind": "node", "at": [1500,2500]}, "attrs": {"label": "V-101"}},
    {"id": "P-1", "type": "pump", "layer": "设备",
     "placement": {"kind": "node", "at": [3500,1500]}, "attrs": {"label": "P-101"}},
    {"id": "pipe-1", "type": "pipe", "layer": "管道",
     "placement": {"kind": "edge", "from": {"node":"V-1","port":"bottom"},
                   "to": {"node":"P-1","port":"in"}, "route": "ortho"}}
  ],
  "annotations": [{"kind": "text", "at": [4200,3900], "string": "进料系统 P&ID", "height": 120}],
  "title_block": {"plant": "甲醇装置", "pid_no": "PID-001", "drawing_name": "进料系统 P&ID", "date": "2026-06"}
}
```
预期自检:report.placed=3(2 node + 1 edge)、skipped=[]、validations 全过。

## 节点符号与 ports(domains/chem)

| type | 形状 | ports |
|---|---|---|
| vessel(容器) | 圆 + 中线 | top / bottom |
| pump(泵) | 圆 + 叶轮 | in / out |
| valve(阀门) | 闸阀(bowtie + 阀杆) | in / out |
| instrument(仪表) | 仪表圈 + stubs | in / out |

edge 的 from/to port 必须用符号声明的 port id(top/bottom/in/out),否则 endpoint unresolved → skip。

## 工具

- `cad_compose_drawing`(MCP,独立容器 `cad:8003`):intent → DXF + PNG,返回
  `{status, dxf, png?, report:{placed, skipped[]}, validations[]}`。错误码同 mine-design。
- `bash`/`read_file`/`present_files`/`ask_clarification`。

## 当前限制(诚实标注)

- 节点符号仅 4 类(vessel/pump/valve/instrument),最小集;换热器/塔/压缩机/反应器待补
- 路由是最小 ortho L 路由:**无避让**(管道可能穿过设备)、**无 port 朝向感知**、无共享管束
- 无仪表回路细节(无控制信号虚线、无联锁标注)
- 设备布置图/管道布置图(按比例 layout)pack 未声明;管段图(isometric)策略未实现
