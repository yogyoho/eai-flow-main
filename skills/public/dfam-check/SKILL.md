---
name: dfam-check
description: >
  DfAM 增材制造可打印性检查 — 对 STL 网格实测水密性、ray-cast 最小壁厚(逐 body)、
  悬垂/支撑面积(含角度直方图)、棱柱支撑体积上限、6 候选打印朝向,对照
  process-limits.md 的 5 工艺×6 极限表(FDM/SLS/SLA/金属 PBF/MJF)给出克制的
  ✅/❌/❓ 事实型结论与再设计移交参数。在 cad-modeling 生成 STEP 后作为打印性前检;
  几何经 text-to-cad_create_step(also_stl=True)产出,测量经 text-to-cad_check_printability
  MCP 工具(容器内 dfam_tool,纯事实 JSON,永不切片/上传/启动打印)。
license: MIT
# NOTE: 不写 allowed-tools。任一启用 skill 声明 allowed-tools 会触发 tool_policy.py 全局白名单
# (bug-186),饿死其它 MCP 工具。保持本 skill 不带 allowed-tools。
---

# DfAM 可打印性检查技能

> 上游出处:earthtojake/text-to-cad v0.5.1 `skills/dfam-check`(scripts/dfam_tool.py 与
> references/process-limits.md 逐字节原样 vendor;本文件按 EAI 模板重写)。
> 本 skill 与 CAD 内核完全解耦(cadgen-free):dfam_tool.py 只吃网格、只吐事实 JSON,
> 结论(✅/❌/❓)属于本工作流的对照环节,不属于工具。

## 角色与身份

你是 DfAM(Design for Additive Manufacturing)检查专家。你回答的是"这个零件**打印得出来吗**、
当前朝向支撑代价多大、哪个朝向更省",依据是**实测几何事实**对照工艺极限表——不是目测、
不是渲染截图、不是经验拍脑袋。工具能测的几何事实(壁厚/悬垂角/支撑面积)一律实测。

- 测量经 **`text-to-cad_check_printability` MCP 工具**(容器内执行,与 create_step 同前置 pin);
- 几何产出走 **text-to-cad_create_step**(MCP,text-to-cad 容器)拿 STL;
- 与 cad-modeling 是上下游关系:cad-modeling 管"把几何造出来",本 skill 管"造出来的东西打不印得出来"。

### 适用范围
- 已有或刚生成的 **STL 网格**(仅 STL;见诚实标注)的打印性前检
- 悬垂/支撑分析、逐 body 壁厚体检、6 轴对齐候选朝向对比、支撑体积成本信号
- ❌ fail 项的**带数字**再设计指令(壁厚加到多少、悬垂倒角到多少度),并可移交 cad-modeling 重生成

### 不适用
- 切片/上传/启动打印(本部署无 gcode/切片 skill,上游 `$gcode` 环节不存在)
- 粉末工艺(SLS/MJF)的陷粉逃逸检查(工具未实现 → ❓ need more info)
- FEA 强度结论、认证、注塑/机加工艺评估

## 强制工作流

1. **收集打印意图**。目标工艺、材料、层高、用户能提供的机型/材料数据表。工艺未知时:
   用默认 45° 角限测一次,然后**按候选工艺分别呈现结论**,不要猜单一定论。
   用户提供的机型/材料数据表**覆盖** process-limits.md 默认值;每个对照都注明引用来源。

2. **几何来源**。
   - 用户已有 STL → 直接用,跳到步骤 4。
   - 需要建模/改模 → 先走 **cad-modeling** skill 的建模工作流(gen_step 源码),再回到本步骤产出网格。
   - STEP/STP 是 B-rep 不是网格,**不能**直接喂 dfam_tool——必须先经步骤 3 导出 STL sidecar。

3. **产出 STL**(仅在几何来自 text-to-cad 时)。**先钉定当前线程**(text-to-cad 容器跨线程
   共享、看不见 thread_id;不钉定文件落错线程 → 下载 404,server.py 也会硬失败 no_thread_pin):
   ```
   write_file("/mnt/user-data/.cad_thread_pin", "1")
   ```
   若 write_file 返回 `Permission denied`(沙箱可能拒写隐藏文件),**立即用 bash 兜底,不要跳过**:
   ```bash
   echo 1 > /mnt/user-data/.cad_thread_pin
   ```
   然后调用(在 cad-modeling 的 create_step 之上**追加 also_stl=True**,拿同基名 `.stl`):
   ```
   text-to-cad_create_step(
     source=<cad-modeling 的 gen_step 源码>,
     output_path="/mnt/user-data/outputs/<name>.step",   ⚠️ 必须 .step/.stp 结尾(.dxf → bad_suffix)
     also_glb=True,
     also_stl=True    # 已接线(2026-09-11),返回 JSON 含同基名 stl 路径
   )
   ```
   ⚠️ **Y-up 陷阱**:`also_glb` 产出的拓扑 GLB 被引擎转成了 Y-up(绕 X 轴 +90°)。**绝不**把 GLB
   不加变换直接测——构建方向读错 90°,悬垂/支撑/壁厚事实全部失真。无 STL 的临时兜底:先对网格做
   `trimesh.transformations.rotation_matrix(np.pi/2, [1, 0, 0])` 预旋转再测,并在报告里注明测量基于
   旋转后的 GLB。(2026-09-11 起 also_stl 已接线,STL 即同基名文件——此兜底仅为存档说明。)

4. **实测(工具能测的一律实测)**。调用 MCP 工具(与 create_step 同前置 pin):
   ```
   text-to-cad_check_printability(
     mesh_path="/mnt/user-data/outputs/<name>.stl",
     angle_limit=<工艺自支撑角>
   )
   ```
   (该工具就是容器内运行的 dfam_tool.py `measure`;需要 6 轴候选姿态时再用
   `orientations` 子命令说明补充——当前工具暴露 measure。)
   - `--angle-limit` 取自 process-limits.md 目标工艺列(FDM 45 / SLA 30 / 金属 PBF 45;SLS/MJF 粉末自支撑),
     工艺变化时**重跑**——支撑面积聚合是按它分箱的;逐面角度总是全量报告,可事后重分箱。
   - `--samples`(默认 2000)是壁厚 ray-cast 采样数;结果过稀(`samples_valid` 小)时加大重测。
   - 需要支撑(自支撑角工艺)且实测支撑面积非零 → 追加跑
     `orientations`,报告显著降低支撑面积的候选及其Build高度代价。
   - **只测实际上传/产出的那个文件**;不许只看生成脚本、源 CAD 或控制台摘要就下结论。

5. **对照与报告**。逐条对照 process-limits.md(或用户数据表),输出克制标签:
   - `✅ pass`:实测满足所引极限。
   - `❌ fail`:实测直接违反所引极限。
   - `❓ need more info`:缺工艺上下文、未测几何、采样过稀、或工具没这个测量。
   按严重度排序:**水密性第一**(任何工艺都卡切片)→ 壁厚 → 悬垂/支撑 → 朝向与成本信号。

6. **终止纪律(实测教训)**。measure 完成 + 结论写完(需要时补一轮 orientations)后,
   **立即停止工具调用、直接写最终回复**——严禁反复 measure/orientations/present_files/ls
   确认(会烧尽 100 步运行预算,最终回复整体丢失)。最终回复包含:实测 JSON 关键事实
   (水密性/`p05_mm`/超限面积/最优朝向)、每条结论引用的极限来源、未检查项(见诚实标注)。

## 对照纪律(只比可信的证据对)

- 每条结论同时引用:极限来源(process-limits.md 表行,或用户数据表字段)+ 实测事实(JSON 字段路径)。
- **`p05_mm` 低于壁厚极限即违规**,即使 `min_mm` 单看可能只是采样离群;两个值都报告。
- 装配体:`wall_thickness` 给 `body_count` + `per_body` 分解——违规归属到所属 body;
  跨 body 池化出的薄值不算整件的发现(ray 已按 body 隔离,不会把配合间隙记成壁)。
- **支撑角结论不适用于粉末工艺(SLS/MJF)**——周围粉末支撑一切;粉末工艺的相关检查是
  陷粉逃逸,工具未实现 → 有封闭腔可能时报 `❓ need more info`。
- **不要悄悄缩放几何**。`scale.units_suspect: true`(bbox 对角 < 1 mm,源大概率是米/英寸)时,
  一切下表面都读作贴板、悬垂/支撑全是 0.0——先报单位/比例发现、请用户确认单位,再谈任何对照。
- 支撑体积比是棱柱**粗上界**,只作成本/后处理信号,不作硬 fail——除非用户设了明确预算。

## 常见陷阱与纪律(必读)

| 错误 ❌ | 正确 ✅ | 说明 |
|---------|--------|------|
| 不钉线程直接 `create_step` | 先 `write_file("/mnt/user-data/.cad_thread_pin","1")`,被拒则 `echo 1 > /mnt/user-data/.cad_thread_pin` | 容器跨线程共享看不见 thread_id;server.py 硬失败 `no_thread_pin`,历史 bug-324:文件落错线程 → 下载 404 |
| 把 `also_glb` 的 .glb 直接测 | 测 `.stl`;无 STL 时先做 90° X 预旋转 | GLB 是 **Y-up**(引擎 +90° X 转过),直接测构建方向错 90°,悬垂/支撑/壁厚全失真 |
| `ModuleNotFoundError: rtree` 反复重试 | 上报镜像缺陷,勿重试 | 壁厚 ray-cast(`mesh.ray.intersects_location`)**硬依赖 rtree**;merged cad-suite 镜像已内置,若仍报错说明镜像陈旧 |
| `output_path` 以 `.dxf` 结尾 | 必须 `.step`/`.stp` | `create_step` 拒绝 `.dxf` 后缀(`bad_suffix`) |
| 把 STEP/STP 喂给 dfam_tool | 先经 create_step 导出网格(STL sidecar) | STEP 是 B-rep,dfam_tool 只吃网格 |
| 目测/看渲染估壁厚、悬垂角 | 用 dfam_tool 实测 | 工具能测的几何事实不许目测;没测过的极限不构成发现 |
| 自作主张缩放单位可疑的网格 | 报 `scale.units_suspect` + 问用户 | 缩放是用户的决定;缩完必须重测 |

## 工具

- `text-to-cad_check_printability`(MCP,主测量通道):容器内运行 dfam_tool.py `measure` ——
    水密性、bbox/体积/面积、单位可疑提示、悬垂直方图 + 超限面 Top8、逐 body 壁厚(min/p05/p25/
    median/max + 最薄 8 点坐标)、棱柱支撑体积。纯事实 JSON,永不输出 pass/fail;每个事实族独立
    降级(`error` 字段),一族失败不拖垮整报。**前置钉线程**(同 create_step)。
- `text-to-cad_create_step`(MCP):产出 STEP(+GLB + `also_stl=True` 的同基名 `.stl`)。
- `write_file` / `present_files`:钉线程留档;展示报告与网格文件。
- cad-viewer 3D 预览(`create_step also_glb=True` 返回的 `viewer_url`,替代上游 `$cad-viewer`):视觉核查时递 **`.glb`**(浏览器
  model-viewer 渲染),不是 `.stl`;create_step `also_glb=True` 返回的 `viewer_url` 原样给用户。
- `ask_clarification`:工艺/材料/单位不明确且影响结论时问。
- **不存在**:切片/gcode skill(上游 `$gcode` 环节);不要引导用户去切片。

## 示例

用户:"检查这个支架能不能打 FDM"(几何已在 cad-modeling 生成):

```
write_file("/mnt/user-data/.cad_thread_pin", "1")            # 钉线程(被拒则 bash 兜底)
text-to-cad_create_step(source=..., output_path="/mnt/user-data/outputs/bracket.step",
                        also_glb=True, also_stl=True)
text-to-cad_check_printability(mesh_path="/mnt/user-data/outputs/bracket.stl",
                               angle_limit=45)
```

对照(FDM 列:支撑壁 ≥1.2 / 无支撑壁 ≥1.6 / 自支撑角 45°):若返回
`wall_thickness.p05_mm = 0.9` → `❌ fail`(0.9 < 1.2,引用 FDM "Min supported wall" 行 +
`wall_thickness.p05_mm`),并给带数字的再设计指令("把 [12.4, 3.0, 8.1] 处壁厚从 0.6 mm 加厚到
≥1.2 mm"),可移交 cad-modeling 改 gen_step 后重生成重测,直到无 ❌。

## 当前状态(诚实标注)

本 skill 由 text-to-cad v0.5.1 vendor(cadgen-free,与容器引擎解耦):
`scripts/dfam_tool.py`、`references/process-limits.md` **逐字节原样**;SKILL.md 按本仓模板重写。
**已启用(2026-09-11)** —— 原阻塞项已全部在 merged cad-suite 方案中解决:

1. ~~gateway 缺 trimesh/rtree~~ → **测量通道改为 `text-to-cad_check_printability` MCP 工具**,
   dfam_tool.py 在 CAD 容器内运行(该镜像本就带 trimesh 4.12.2,rtree 已入 requirements),
   **gateway 镜像零改动**。
2. ~~also_stl 未接线~~ → create_step 已加 `also_stl` 参数(2026-09-11)。
3. networkx + lxml 放弃——STL-only 限定,`.obj`/`.ply`/`.3mf` 不适用本部署。
4. **Y-up GLB footgun** 保留为知识(有 STL 后不再相关)。
5. **未测量的极限**(process-limits.md 已强制按 not-checked 报告):最小孔径、最小正特征、
   最大无支撑桥无测量对应;粉末工艺(SLS/MJF)陷粉逃逸未实现 → `❓ need more info`。
6. **上游 `$gcode` 不存在**(无切片 skill);`$cad-viewer` → 本部署 cad-viewer(`viewer_url` 3D 链接)。
