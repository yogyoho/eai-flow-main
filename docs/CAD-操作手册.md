# CAD 功能与技能调用操作手册

> 适用版本: 2026-09-12（cad-suite 合并架构 + 上游 v0.5.1 参考快照）
> 读者: 平台使用者（业务/工程）、提示词编写者、运维
> 本手册描述当前部署的真实可用状态;标注 ⏸ 的为已 vendor 但默认关闭的能力。

---

## 1. 能力总览

平台内 CAD 能力由一个合并容器 **cad-suite** 承载（`eai-flow-cad-suite`），内部三个服务:

| 服务 | 端口 | 职责 |
|------|------|------|
| text-to-cad MCP | :8004 | 3D 建模生成（STEP/STL/GLB）、几何检查、快照渲染、标准件库、DfAM 事实、通用 DXF |
| cad / EDP MCP | :8003 | 2D 工程图纸（域包: 矿山 `mine-design`、化工 `chemplant-design`）+ DXF 解析 |
| cad-viewer | :4178 | 浏览器 3D 预览（GLB） |

Agent 通过 **6 个 MCP 工具** + **10 个技能** 使用以上能力。用户不需要知道工具名——
**在对话里用自然语言描述需求即可**，技能会被自动检索并接管工作流。

### 工具清单（供排查参考，日常无需记忆）

| 工具 | 作用 | 关键参数 |
|------|------|---------|
| `text-to-cad_create_step` | build123d 源码 → STEP（+GLB +STL） | `source`（含 `gen_step()`）、`output_path`（.step/.stp）、`also_glb`、`also_stl` |
| `text-to-cad_inspect_step` | 几何事实检查 | `step_path`、`subcommand`(refs/measure/align/frame)、`facts` |
| `text-to-cad_snapshot_step` | STEP → PNG 快照（agent 自己看图自检） | `step_path`、`output_path`(.png)、`camera` |
| `text-to-cad_create_dxf` | ezdxf 源码 → 2D DXF | `source`（含 `gen_dxf()`，返回 ezdxf 文档）、`output_path`(.dxf) |
| `text-to-cad_check_printability` | DfAM 打印可行性事实 | `mesh_path`(.stl)、`angle_limit` |
| `text-to-cad_search_step_parts` | 标准件目录搜索/下载 | `query` / `download_id`+`output_path`、`standard` |

### 技能清单

| 技能 | 状态 | 一句话 |
|------|------|--------|
| `cad-modeling` | ✅ | 3D 建模主技能: 5 步强制工作流 |
| `cad-dxf` | ✅ | 通用机械 2D DXF |
| `step-parts` | ✅ | 标准件目录检索纪律 |
| `dfam-check` | ✅ | 打印可行性检查 |
| `cad-urdf` / `srdf` / `sdf` | ✅ | 机器人描述 / 语义帧 / Gazebo 仿真模型 |
| `implicit-cad` | ✅ | GLSL SDF 隐式 CAD（浏览器渲染） |
| `sendcutsend` | ✅ | 激光切割下单前检查（下单需用户自行操作） |
| `gcode` / `bambu-labs` | ⏸ 禁用 | 需要切片器 CLI（部署未装，启用需立项） |

---

## 2. 访问入口

| 页面 | 地址 |
|------|------|
| 登录 | `http://localhost:2026/login`（账号向管理员索取） |
| **AI 对话（新会话）** | `http://localhost:2026/workspace/chats/new` |
| 会话列表 | `http://localhost:2026/workspace/chats` |
| 3D 预览 viewer | 对话回复中的 **viewer_url 链接**直接点开（底座 `http://localhost:4178`） |

- `localhost` 与 `127.0.0.1` 均可（bug-3306 修复后两者等价）。
- 对话页右下角显示当前模型（如 Agnes-2.5-Flash）。复杂模型建议切换更强档位。

---

## 3. 快速上手（5 分钟）

1. 登录后打开 `/workspace/chats/new`。
2. 粘贴一段提示词（见 §9 提示词库，或自己描述）:

   ```
   用 build123d 生成一个 80×50×30 的安装板，四角各一个 Φ6 通孔，导出 STEP 和 GLB，
   给我 3D 预览链接，并报告体积自检结果。
   ```

3. agent 会自动: 列出默认假设（没写的尺寸按 **mm / XY 基面 / +Z 拉伸**处理）→
   参数化建模 → 导出 → 几何自检 → 回复。
4. 最终回复包含: 文件清单（.step/.glb）、体积/包围盒事实、**加粗的 viewer_url**。
5. 点 viewer_url → 浏览器打开 3D 旋转预览;文件在回复的"已编辑文件"卡片中可下载。

**微调用追问**: "把高度改到 40"、"孔改成 4×Φ8"、"再加一个 Φ20 中心孔"——agent 会在
同一对话内改源码重新生成。

---

## 4. 3D 建模（cad-modeling 技能）

### 4.1 五步强制工作流

| 步 | 内容 | 要点 |
|----|------|------|
| 1 brief | 明确需求 | 信息不足时 agent 只问 **1 个**聚焦问题;其余按默认假设推进并明示 |
| 2 建模 | `def gen_step():` 源码 | 参数化命名、闭合正体积、`from build123d import *` 首行 |
| 3 导出 | **先钉线程**，再 `create_step` | `.cad_thread_pin` 写入（失败则 bash `echo 1 >` 兜底）;`.dxf` 后缀会被拒 |
| 4 自检 | `inspect refs --facts`（不可省略） | 体积/包围盒与设计意图做数学比对;**refs 通过 ≠ 实体有效**，源码里 `assert shape.is_valid`（属性，别加括号） |
| 5 交付 | present_files + viewer_url | 都不可省略;通过后**立即停工具写回复**（防循环烧尽步数预算） |

### 4.2 默认假设（未指定时）

单位 mm;基准面 XY、拉伸方向 +Z;原点=主零件中心;几何为闭合正体积实体;
外观细节（圆角/漆面/标识）不做。

### 4.3 装配

描述为多零件即可（"底板 + 上面立柱，作为装配导出"）——gen_step 返回带标签
`Compound`（`Compound(label="asm", children=[a, b])`，成员先设 `.label`）。
**不要说"用 Compound.assemble"**（build123d 无此 API）。

### 4.4 常见坑（技能已内置防御，了解即可）

| 坑 | 正确做法 |
|----|---------|
| `shape.is_valid()` 调用形式 | `shape.is_valid` 是**属性**，加括号 → TypeError → run_failed |
| `ThreadedHole` / `Counterbore` / `Countersink` | 用 `Hole(radius)` / `CounterBoreHole` / `CounterSinkHole` |
| `Hole(diameter=8)` | Hole 用**半径**: Φ8 = `Hole(4)` |
| 螺纹建模 | 不建模螺纹，通孔+工程图标注 |

---

## 5. 快照渲染（agent 的眼睛）

在对话中说: **"渲染一张 PNG 快照给我/确认外观"**。

- agent 调 `snapshot_step`（无头 Chromium 离线渲染 STEP→PNG），把图贴进回复供人机共看
- 简单零件 1 张 iso 即可;装配/多孔/壳体建议多角度
- 渲染通过即交付，勿反复渲染（浪费步数）

---

## 6. 标准件库（step-parts）

直接说: **"在 step.parts 库搜 M8 六角螺栓，下载 STEP"**。

- 目录 16800+ 标准件（螺钉/螺栓/轴承/电机/连接器），支持 `standard` 过滤（如 "ISO 4762"）
- 下载的 STEP 可继续说"导入这个螺栓到我的装配里"
- 需要外网（api.step.parts）;下载自带 SHA-256 校验
- 纪律: 搜索命中多义时 agent 会给 Top-3 候选;检索不到≠不存在（网络失败重试一次再下结论）

---

## 7. 打印可行性（dfam-check）

两步: **"生成 40×40×3 薄板，STL 也要导出，然后做 FDM 打印可行性检查"**。

- create_step 以 `also_stl=True` 产 STL → `check_printability` 输出**纯事实 JSON**:
  水密性、逐体壁厚（min/p05/median/max）、悬垂面积+角度直方图、支撑体积估计
- 事实只测不判——agent 对照内置工艺限值表（FDM/SLS/SLA/金属 PBF/MJF）给
  `✅ pass / ❌ fail / ❓ need more info` 三态结论，并注明所引极限来源
- 明确不测: 孔径、正特征、无支撑桥（按 not-checked 报告）

---

## 8. 2D 图纸（两条路线，先选对）

| 需求 | 用哪条 | 说明 |
|------|--------|------|
| 通用机械 DXF（垫片/面板/样板/下料/切割轮廓） | `cad-dxf` 技能 → `create_dxf` | gen_dxf() 返回 **ezdxf 文档**;纯几何无图签 |
| 带图签/标注的**工程图**（矿山布置/化工图） | `cad_compose_drawing`（cad :8003） | 技能 `mine-design` / `chemplant-design` |
| 3D 零件的平面投影 | 先 cad-modeling 出 STEP，再说"生成它的展开/投影 DXF" | DXF 轮廓从真实拓扑换算 |

⚠️ 方向性错误会被护栏拦住: `create_step` 拒 `.dxf`、`create_dxf` 只收 `.dxf`。

---

## 9. 提示词库（复制即用）

### 9.1 基础零件
```
用 build123d 生成一个 80×50×30 的安装板，四角各一个 Φ6 通孔（边距 8mm），
导出 STEP 和 GLB，给我 3D 预览链接，并报告体积自检结果。
```

### 9.2 装配体
```
建一个装配体: 底板 80×40×6，上方中央放一个 20×20×20 的立方凸台（下表面贴合
底板上表面），作为一个装配导出 STEP + GLB，给我预览链接，并用 inspect 确认
装配里有两个对象。
```

### 9.3 配电柜（钣金柜体）
```
用 build123d 给我建一个动力配电柜柜体（mm）:
- 外形 800 宽 × 600 深 × 2000 高，钣金壁厚 3mm，五面封闭，正面开口装门
- 内部安装板 750×550×3，距背面 100mm
- 门板 798×1990×3 独立零件，与柜体组成装配，右缘 120×40×10 门把手
- 两侧下半部各 4 条 200×20 长圆通风孔（竖向均布，边距 50）
- 底板 3 个 Φ50 电缆进线孔沿深度中线均布
导出 STEP + GLB，做 inspect 自检，给我 viewer 链接和文件。
```

### 9.4 标准件引入
```
在 step.parts 库搜索 M8 六角螺栓（hex bolt），挑一个下载 STEP，
告诉我零件名/标准号/体积，然后把它和一个 60×40×5 底板组成装配导出。
```

### 9.5 打印可行性
```
生成 40×40×3 薄板（STL 也要导出），做 FDM 打印可行性检查，
报告壁厚和悬垂事实，按 pass/fail/need-info 三态给结论。
```

### 9.6 通用 DXF
```
生成一个 60×40 矩形、四角 R5 圆角的垫片 DXF（通用机械轮廓，无图签），
cut 层放闭合切割轮廓，输出 DXF 文件并说明校验情况。
```

### 9.7 快照追加
```
给刚才的模型渲染一张 PNG 快照，确认外观。
```

---

## 10. 输出物与文件去向

| 产物 | 位置 |
|------|------|
| STEP/GLB/STL/PNG/DXF | 线程工作区 `outputs/`（回复的"已编辑文件"卡片可下载/预览） |
| 3D 预览 | viewer_url（GLB 的公开镜像副本，浏览器直开） |
| 建模源码 | 同目录 `<名>.py`（可复用/改参重生成） |

---

## 11. 故障排查 FAQ

| 症状 | 原因 | 处置 |
|------|------|------|
| 回复出现 `bad_suffix` | output_path 后缀错（.step 工具拒 .dxf，反之亦然） | 改后缀重发 |
| `no_thread_pin` | 跨线程容器需 pin 定位线程目录 | agent 会自动补写（write_file 被拒时 bash `echo 1 >` 兜底） |
| `run_failed` + `TypeError ... is_valid` | build123d 0.11 is_valid 是属性 | 技能陷阱表已防御;老对话重开新会话 |
| `run_failed` + `Compound has no assemble` | 臆造 API | 用 `Compound(label=, children=[])` |
| 回复出现 "Tool ... is deferred ... Call tool_search first" | 工具 schema 懒加载提升机制（P3 已知瑕疵，agent 会自恢复后重试） | 忽略;若中断则重发请求 |
| 回复末尾 "Recursion limit of 100 reached" 且无最终结论 | 模型循环烧尽步数（裸 API 默认 100 才会发生;**UI 已内置 1000**，正常不触发） | 换强模型档位或简化需求重试 |
| 生成的是 2D 图但想要 3D | 提示词含"DXF/图纸"会分流 2D | 明确说"3D 模型/STEP" |
| 点 viewer_url 打不开 | viewer 容器未起 | 运维: `docker compose -p eai-docker up -d cad-suite` |
| 页面能看但点了没反应 | （历史 bug-3306）访问 host 不在 dev origin 白名单 | 已修;若复发检查 next.config.js allowedDevOrigins |

---

## 12. 运维须知

- **容器**: `eai-flow-cad-suite`（三服务合一，supervisor 全组同生共死）
  `docker compose -p eai-docker restart cad-suite` 整组重启;端口 8004/8003 内网、4178 host
- **镜像重建**（改 server.py/依赖后必须）:
  `docker compose -p eai-docker -f docker/docker-compose-dev.yaml build cad-suite`
  再带全 `-f` overlay `up -d cad-suite`（离线部署按 offline-export.sh 单镜像交付）
- **数据**: 三服务共享 `backend/.deer-flow:/data`（线程目录即文件落点）
- **参考快照**: `text-to-cad-main/`（上游 v0.5.1，gitignore，只读参考勿改）
- **禁用技能**: `gcode`/`bambu-labs` 等切片器层（启用 = cad-suite 装 CuraEngine/OrcaSlicer
  + 包 slice 工具 + 真机 profile，另立项）
- **网关缓存**: 改 MCP server.py 的工具 docstring 后需 `docker compose -p eai-docker restart gateway`
  才会重新发现工具

---

## 13. 已知限制（诚实清单）

- `snapshot` 渲染为静态 PNG（GIF 轨道未暴露）;diff 子命令未暴露
- 2D 工程图（图签/标注）仅 mine/chem 两个域包;通用电气一次图无域包
- DFAM 检查 STL-only;孔径/正特征/桥不测
- 切片器/打印机链路未部署（gcode/bambu-labs 禁用）
- 上游 v0.5.1 已重写为 cadgen 引擎，与本部署 vendored 0.3.6 引擎**不兼容**——
  参考快照仅作对照，将来对齐属独立迁移项目
- flash 级模型在复杂需求上有输出方差（如漏写 viewer_url 文案、DXF 场景偶尔绕过工具）;
  重要交付建议用更强模型档位
