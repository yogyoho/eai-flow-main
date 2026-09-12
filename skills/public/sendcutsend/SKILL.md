---
name: sendcutsend
description: >
  SendCutSend.com 下单前预检 — 用官方 ordering guide/catalog/specs 三份公开证据源,评审 DXF
  (激光平板切割)与 STEP/STP(CNC 路由)上传件的就绪性:上传格式、材料/SKU/厚度/服务可用性、
  弯曲/攻丝/沉孔/压铆/嵌件/表面处理等服务专项检查,产出带引用的预检报告。STEP 几何事实经
  text-to-cad_inspect_step 在 CAD 容器测量。仅用于 SendCutSend 预检;询价/下单由用户用自己
  的账号在浏览器完成,agent 不接触凭据。
license: MIT
# NOTE: 不写 allowed-tools。任一启用 skill 声明 allowed-tools 会触发 tool_policy.py 全局白名单
# (bug-186),饿死其它 MCP 工具。保持本 skill 不带 allowed-tools。
---

# SendCutSend 下单前预检技能

## 来源与适配(EAI-CUSTOM)

Provenance: adapted from [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad)
`skills/sendcutsend`(0.3.6 树,MIT,许可证见 `LICENSE`)。EAI-CUSTOM 适配(2026-09-11):

- `$cad` 后端映射 → STEP/STP 几何事实走 `text-to-cad_inspect_step`(独立 CAD 容器);几何修正/
  重建走 `text-to-cad_create_step`;建模纪律见同级 skill `cad-modeling`。
- 上游的 agent 侧本地几何脚本(直接 `import build123d` / `import ezdxf`)全部移除:gateway 镜像缺
  libGL,`import build123d` 当前直接失败(libgl1 加包重建走单独修复线);agent 沙箱无 ezdxf 执行
  → DXF 侧仅纪律性指导(见"诚实标注")。
- 官方源抓取 → `web_fetch`(真实浏览器 UA)或带 browser UA header 的 urllib;默认 Python UA 被
  CDN 403(2026-09-11 实测)。
- `$cad-viewer` 移交 → 诚实降级(本部署无此工具,报告显式文件路径);图像生成诊断图 → 可选降级。
- `references/` 两份上游文件逐字保留;其中的 `$cad` / `build123d` / `ezdxf` / `$cad-viewer` 字样
  按上表映射理解。

用本 skill 产出保守、证据引用的 SendCutSend 预检报告(针对 DXF 与 STEP/STP 上传件)。

把 SendCutSend 的 ordering guide、catalog JSON、specs JSON 当作**证据源,不是稳定 API**。字段名、
类型、覆盖面都会变。不要把缺失、解析失败、`N/A` 或互相冲突的源数据变成 pass 或 fail。直接从官方
URL 抓源;本地检视只用于测量具体文件事实;最终报告只从显式比对写出。

## 强制工作流

1. **收集下单意图**。
   - 激光平板切割 / 2D 板件轮廓 → 倾向 DXF;CNC 路由 / 3D 模型上传 → 倾向 STEP/STP。
   - 记录:文件类型、目标工艺、材料/SKU、厚度、数量、服务(bending / tapping / countersinking /
     hardware insertion / finishing)、表面处理。
   - 下单语境缺失或含糊 → 先从源数据整理出具体候选项(SKU/材料/厚度/服务 + 源链接;specs JSON
     的 `photo_url` 图片与 `learn_more_url` 链接一并给出),再问用户确认,**然后才写就绪结论**。

2. **抓取官方证据源(每次评审前都要重抓)**。按 `references/official-sources.md` 的三个官方 URL
   直接抓取并检视:
   - 通道纪律:用 `web_fetch`(自带真实浏览器 UA)或 python urllib **显式加 browser UA header**。
     ⚠️ 默认 Python-urllib UA 对全部三个 cdn.sendcutsend.com/specs URL 返回 **403**(2026-09-11
     实测);browser UA 返回 200。三份文件公开、无鉴权。
   - 报告 bibliography 记录源 URL、访问日期、JSON `_meta` 值。
   - 任一源抓不到 → 报告"当前官方源不可用",依赖该源的检查**不得给 ready 结论**。

3. **钉定线程(强制 —— 任何 text-to-cad_* 调用之前)**。text-to-cad 容器跨线程共享、看不见
   thread_id;不钉定会把文件写进错误的线程目录 → 下载 404(bug-324):
   ```
   write_file("/mnt/user-data/.cad_thread_pin", "1")   # sandbox 解析到当前线程的 user-data/
   ```
   若 write_file 返回 `Permission denied`(沙箱可能拒写隐藏文件),**立即用 bash 兜底,不要跳过**:
   ```bash
   echo 1 > /mnt/user-data/.cad_thread_pin
   ```

4. **测量上传文件本身(fact-only,不许只看生成器)**。检查的必须是**要上传的那个文件**——不要只
   检查源生成器、CAD 模型或生成器控制台摘要。
   - **STEP/STP(CNC 路由路径,本部署可完整执行)**:
     ```
     text-to-cad_inspect_step(step_path="/mnt/user-data/.../<name>.step", subcommand="refs", facts=True)
     ```
     `refs --facts` 给体积、包围盒、面/边计数;测两点距离/对齐 → `subcommand="measure"`/`"align"`
     + selectors。弯曲在范围内时:refs 的 face 选择器暴露 `surfaceType` 与邻边信息 → 找圆柱/环面
     折弯面提取半径,分组重复半径,与所选 SKU 的 `bending_specs.effective_bend_radius` /
     `bending_specs.bend_radius` 比对。
   - **几何修正 / 重建上传候选** → 写 build123d 源码(定义 `def gen_step():`)交
     `text-to-cad_create_step` 在容器执行(output_path **必须 `.step`/`.stp` 结尾**,默认
     `also_glb=True`;纪律同 cad-modeling)。**绝不在 agent 侧 python 里 import build123d**
     (gateway 缺 libGL,import 必失败);**绝不把 `.dxf` 传给 create_step**(返回 `bad_suffix`)。
   - **DXF(激光切割路径)**:本部署 DXF **没有确定性测量通道**(见"诚实标注")→ 按"DXF 检查
     清单"逐条列出待测事实;有测量值的行给值,**测不到的行一律 `❓ need more info`,不得目测放行**。
   - 每个检视 helper 保持 **fact-only**:只报测量值、解析错误与局限,**不得输出 pass/fail/ready**。

5. **证据比对(只比可信配对)**。
   - 先判断该检查是否适用;引用源字段路径或 guide 章节;引用实测文件事实;**源要求与实测事实都
     可信且齐全才比**,缺任一侧 → `❓ need more info`(STEP 侧可补一次针对性 inspect;DXF 侧
     如实标注缺测)。
   - 实测的上传风险、可制造性问题、违反引用要求 → 一律按 `❌ fail` 处理,不要猜 SendCutSend UI
     会怎么分类。
   - **DXF 单位**:`$INSUNITS`、header extents、实测 bounds、下单语境放在一起看。`$INSUNITS`
     缺失、不支持、或不是 guide 认可的 DXF 单位码(`1` 英寸 / `4` 毫米)→ 报单位/比例错误,建议
     重新导出或确认单位,**之后才**继续尺寸/折弯/材料专项比对。不得默默缩放几何、不得用不确定的
     比例下材料级 pass/fail 结论。
   - **2D 折弯线与折边长度**:每条折弯线逐段测折边长。测折弯线两侧最近的切割/自由边(含 notch、
     slot、gap、split tab、cutout 等中断折弯段或形成局部自由边的几何),局部最小折边深度对比
     `bending_specs.min_flange_length_before_bend` / `min_flange_length_after_bend`。普通
     enclosed holes / interior cutouts **不套**折边长度限制,除非有该服务的 hole-to-bend /
     feature-to-bend 引用规则;有则按规则用 centerline-to-bend 或 edge-to-bend 测量单独报。
     附近折弯邻接切割几何不得只当 corner relief——除非剩余局部折边仍过最小值。任一局部折边深度
     低于 SKU 最小值 → `❌ fail`。导出几何有局部 cutout / 中断折弯 / split 折弯段 / relief /
     tab / unsupported region 时,不得依赖源级汇总值。
   - **折弯发现按物理成因分行**,不得把折弯邻接几何塌缩成笼统的 flange fail:最小折边/接触长度
     错误、折弯线或 die-area 几何穿越、邻近自由边或 cutout 造成的折弯接触/支撑不足、折弯线未覆盖
     折弯区、split/common-axis 折弯段、切割几何接触或穿越折弯线,各占一行。源未暴露确切
     die-area/接触阈值时,把实测文件事实标为 direct file inspection 并显式标注源受限。
   - **STEP/STP 折弯半径**:模型含钣金折弯几何或目标服务含折弯时,提取圆柱/环面折弯面及其半径
     (inspect refs 的 face 选择器),分组重复半径,与 SKU 的 `bending_specs.effective_bend_radius`
     / `bend_radius` 比对。材料/SKU 未知 → 报实测半径集合,先要材料/厚度再下就绪结论。实测半径
     与 SKU 刀具半径冲突 → 报 bend-radius mismatch 错误。

6. **写报告交付,然后停**。报告含:文件路径、假定服务、材料/下单语境、查过的源文件 + 访问日期、
   实测几何事实、按实际影响排序的发现、具体下一步修改。发现表加 `Rule source` 列:Markdown 链接
   到源 URL + 该行用的 JSON 字段路径或 guide 章节;仅基于直接文件检视、无外部规则的行写
   `Direct file inspection`,不许留空。结构化报告用 `references/report-template.md`。**产出或
   修改过上传候选时,交付必须给显式文件路径**(STEP 另附 create_step 返回的 `viewer_url`;本部署
   无 `$cad-viewer`,不得假装移交成功)。**不是每条必需引用检查都 pass(或明确不在所选服务范围)
   就不许说 "SendCutSend ready"**。
   **终止纪律(实测教训)**:源抓取 + 测量 + 比对完成后,**立即停止工具调用、直接写最终报告**——
   最多再补一轮 inspect 或补抓一次源,严禁反复 inspect / 反复重抓官方源 / ls 确认(会烧尽 100 步
   运行预算,run 以 recursion limit 报错,最终报告整体丢失)。

## 状态标签(只用这三个)

- `✅ pass`:实测文件事实满足被引用的当前要求。
- `❌ fail`:实测上传风险、可制造性问题、或直接违反被引用的当前要求。
- `❓ need more info`:缺语境、缺源证据、未测几何、源冲突、或工具局限。

## DXF 检查清单(激光平板切割)

从最新抓取的源与实测 DXF 几何事实出发,检查:

- 单个可上传 DXF 文件,模型几何 1:1 比例
- 单位与整体零件尺寸;`$INSUNITS` 缺失、不支持、异常 → 按比例错误处理,直到用户确认单位
- 服务要求闭合轮廓时,切割轮廓闭合
- 退化或零面积闭合轮廓、两点闭合折线、奇数度切割端点
- 重复或重叠切割几何
- 不支持的注释、文字、尺寸标注、图片、构造线、隐藏指令图层
- ordering guide 与上传工作流的图层/颜色/线型约定
- 折弯范围内:折弯线实体、折弯段长度、split/common-axis 折弯、每条折弯线两侧局部折边深度、最近
  非折弯切割边或 cutout 距离、折弯线覆盖范围、折弯接触/支撑不足、die-area 或折弯邻接切割几何
  穿越、切割几何接触或穿越折弯线
- 最小孔、槽、web 宽度、内部几何、零件密度、排样、间距——仅在源事实与实测文件事实都支持比对时
- 请求了二级服务(折弯/攻丝/沉孔/嵌件/表面处理/去毛刺)时,对应二级服务要求

## STEP 检查清单(CNC 路由 / 3D 模型上传)

从最新抓取的源与实测 STEP 几何事实出发,检查:

- STEP/STP 可读且是实体(solid),不是松散曲线或曲面
- 单位、比例、包围盒、厚度、特征尺寸
- 折弯范围内测钣金折弯半径;实测圆柱折弯面半径对比 SKU 的
  `bending_specs.effective_bend_radius` / `bend_radius`
- 尖内角、小孔/槽、薄壁、孤岛、深腔、刀具可达性、公差——仅当文件检视能测出该事实
- 几何其实是板件轮廓、用 DXF 激光切割更合适的情况
- 材料、厚度、表面处理、二级服务兼容性

## 诊断图(可选,降级)

发现配图更易理解时,若图像生成/图像编辑能力可用,主动产一张简洁诊断图(不必等用户要求):出现
`❌ fail`、空间上含糊的几何问题、需要 before/after 解释的几何修改时。生成前做布局预检:选最少的
callout;标签会挤/叠/出画布 → 改编号标记 + 侧边图例、更大画布、或分开的细节视图;测量值与规则
文字放图例,不压密集几何;包含实测失败距离、引用最小值、建议的移动/间隙目标。生成后先检视再交付;
标签叠/裁/难读/遮几何 → 重生成或修改。**无图像生成能力时**:报告里说明该局限,并用文字描述本要
画的图。

## 常见陷阱(每次评审前过一遍)

| 错误 ❌ | 正确 ✅ | 说明 |
|---------|--------|------|
| 把 `.dxf` 路径传给 `text-to-cad_create_step` | output_path 必须 `.step`/`.stp` 结尾 | `create_step` 拒绝 `.dxf`,返回 `bad_suffix`;本平台没有任何 MCP 工具能写/收 DXF |
| agent 侧 python `import build123d` 测几何 | 事实走 `text-to-cad_inspect_step`;重建走 `text-to-cad_create_step` | gateway 镜像缺 libGL,`import build123d` 当前直接失败(libgl1 修复线另开);agent 沙箱也没有 CAD 内核 |
| 沙箱里跑 ezdxf 脚本写/测 DXF | DXF 侧按纪律性指导做,事实缺失就 `❓` | agent 沙箱无 ezdxf 执行;flat-pattern DXF 编写/修正仅是纪律性指导,不是可执行路径 |
| `shape.is_valid()` | `shape.is_valid` | **is_valid 是属性不是方法**(gen_step 源码里写断言时),调用形式抛 `TypeError: 'bool' object is not callable` → run_failed |
| `Compound.assemble([...])` | `Compound(label="asm", children=[a, b])` | build123d 没有 `Compound.assemble`(AttributeError) |
| `ThreadedHole` / `Counterbore` / `Countersink` / `diameter=` | `Hole(radius)` / `CounterBoreHole(...)` / `CounterSinkHole(...)` / 用半径 | 这些名字 build123d 不存在;Hole 系列全用半径 |
| gen_step 源码缺 `from build123d import *` | 源码第一行必须 `from build123d import *` | 否则 `BuildPart`/`Box`/`Hole` 全部 NameError |
| 默认 Python UA 抓 cdn.sendcutsend.com | `web_fetch` 或 urllib + browser UA header | 默认 UA 三个 URL 全 403(2026-09-11 实测);browser UA 200 |
| 替用户登录 sendcutsend.com / 索要或保存账号凭据 | 询价/下单由用户在自己浏览器完成 | agent 不接触任何 SendCutSend 凭据;平台无 quoting/order API 工具 |
| 用 raw text parsing / 替代几何后端凑几何事实 | 事实走确定性工具;测不了如实 `❓` | 上游纪律:几何事实不拿文本解析凑数、不拿"大概"放行 |
| 调 text-to-cad_* 前忘钉线程 | 先写 `/mnt/user-data/.cad_thread_pin` | 不钉定 → 文件落错线程目录 → 下载 404(bug-324) |

## 工具

- `text-to-cad_inspect_step`(MCP,独立 CAD 容器):STEP/STP 事实测量主通道。`subcommand` ∈
  `refs`/`measure`/`align`/`frame`;`selectors` 为 `#o1.2.f1` 类选择器(refs 的 face 选择器带
  surfaceType 与邻边信息,折弯半径提取靠它);`facts`/`detail` 仅 refs;refs 需 STEP 有同基名
  `.glb`(即由 create_step `also_glb=True` 产出)。返回 inspect JSON,或 `{status:"error",...}`。
- `text-to-cad_create_step`(MCP,同容器):需要产出/重建上传候选时用。写 `def gen_step():`
  build123d 源码,`output_path` 必须 `.step`/`.stp` 结尾,`also_glb=True` 拿 `viewer_url`。
  返回 `{status, step, glb?, public_glb?, viewer_url?}`;失败 `{status:"error",...}`
  (`resolve_failed`/`bad_suffix`/`run_failed`/`no_thread_pin`)。
- `text-to-cad_search_step_parts`(MCP,同容器):查 step.parts 标准件库(紧固件/轴承/电机/连接器)。
  可选——为装配建模取真实五金 STEP 参考(需网络)。
- `web_fetch`:抓三份官方源(ordering guide MD / catalog JSON / specs JSON,公开无鉴权)。
- `bash` / `read_file` / `write_file`:钉线程文件、留档测量脚本与报告草稿。
- `present_files`:展示报告与产出文件。
- `ask_clarification`:下单语境缺失/含糊、且候选选项已整理好时问。

## 当前状态(诚实标注)

本 skill 由 text-to-cad 0.3.6 上游适配,EAI-CUSTOM 2026-09-11。**可用**:

- **STEP/STP(CNC 路由)预检全链路可执行**:`text-to-cad_inspect_step` 事实(refs/measure/align/
  frame)+ 三份官方源比对 + 引用式报告。
- **证据源抓取**:三份 cdn.sendcutsend.com/specs 文件公开、无鉴权;需 browser UA(`web_fetch`
  自带;urllib 手动加 header),默认 Python UA 403(2026-09-11 实测)。
- **上传候选重建**:`text-to-cad_create_step`(build123d 在 CAD 容器执行),.step + `viewer_url`。

**本部署不可用 / 降级(必须如实报告,不得假装可用)**:

- **下单与询价不在 agent 能力内**:SendCutSend 报价/下单需要**用户自己的账号**,并由用户在自己
  浏览器里完成外部网络操作;agent 不持有、不索要、不保存任何 SendCutSend 凭据。本平台没有
  quoting/order API 工具——本 skill 只做上传前预检,下单永远由用户手动完成。
- **DXF 几何测量无确定性执行通道**:没有 MCP 工具接受 DXF(`create_step` 对 `.dxf` 返回
  `bad_suffix`);agent 沙箱无 ezdxf 执行。flat-pattern DXF 的编写/修正指导仅为**纪律性指导**
  (discipline-only):告诉用户/上游工具该测什么、该改什么;DXF 事实行没有测量值时必须
  `❓ need more info`,不得放行。
- **gateway 侧 build123d import 当前失败**(gateway 镜像缺 libGL —— libgl1 加包重建由单独修复线
  处理):**任何几何脚本一律走 `text-to-cad_create_step` 容器路径,不要在 agent 侧 python 里
  import build123d**。
- **`$cad-viewer` 移交不可用**:本部署无 cad-viewer MCP 工具 → 报告显式文件路径;STEP 预览用
  create_step 返回的 `viewer_url`。
- **图像生成诊断图**:能力存在才用,否则文字降级(见上节)。
- **SendCutSend 是美国制造服务**(USD 计价、美国/加拿大物流,无中国物流):本 skill 预计更多用于
  其通用激光切割/CNC 可制造性规则与预检纪律,而非实际下单。

## References

- 官方源选择:`references/official-sources.md`(上游逐字保留)
- 报告结构:`references/report-template.md`(上游逐字保留)
