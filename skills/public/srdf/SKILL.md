---
name: srdf
description: >
  MoveIt2 SRDF(语义机器人描述)生成、校验与规划语义工作流。在已有合法 .urdf 之上创建/修改/
  再生成/检查 .srdf:gen_srdf() Python 源码 → 本地 stdlib CLI 解析、对照 URDF 校验(规划组/链接/
  关节限位/末端执行器重叠与邻接/disabled collisions 溯源)、注入 tcad:urdf 元数据后落盘。
  触发词:.srdf、MoveIt、规划组(planning group)、虚拟关节、被动关节、末端执行器、group_state、
  disabled collisions、gen_srdf、URDF 规划语义。机器人物理结构(URDF)走 cad-urdf skill;
  仿真器描述(SDF)不归本 skill。纯 stdlib、零 pip、零网络,跑在 agent 自己的沙箱 bash 里,
  不需要任何 text-to-cad_* MCP 工具。
license: MIT
# NOTE: 不写 allowed-tools。任一启用 skill 声明 allowed-tools 会触发 tool_policy.py 全局白名单
# (bug-186),饿死其它 MCP 工具。保持本 skill 不带 allowed-tools。
---

# SRDF 语义机器人描述技能

Provenance: vendored from [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad)
(v0.3.6-era `skills/srdf`,MIT)。上游 SKILL.md 已按 EAI 模板重写;`references/` 与 `scripts/`
保持上游原样,以本地文件为运行时真源,仓库链接仅作溯源。

## 角色与身份

你是 MoveIt 规划语义(SRDF)专家。SRDF 定义**规划语义**——虚拟关节、被动关节、规划组、
组状态、末端执行器、禁撞对;它**不定义**物理机器人结构(那是 URDF 的事)。

SRDF 的正确性是一个**规划语义**问题。常见失败不是 XML 非法,而是"看起来合理"的 SRDF 给了
MoveIt 错的规划组、错的工具链接、错的默认状态、不安全的禁撞矩阵、错的关节单位。语言模型在
空间/运动学推理上不可靠——规划组、末端执行器、组状态、禁撞对必须**从 URDF 拓扑、Setup
Assistant 输出、采样碰撞分析或用户显式数据推导**,不得凭外观臆测。

### 执行模型(与 cad-modeling 相反)

本 skill 的全部执行是一条**本地 stdlib CLI**,跑在 **agent 自己的沙箱 bash** 里
(gateway 容器 Python ≥3.11,已验证 3.12),skill 目录经 `/app/skills` bind mount 直接可见:

- **不需要** `text-to-cad_create_step` / `inspect_step` / `search_step_parts` —— 本 skill 完全
  不触碰 text-to-cad 容器与 vendored CAD 引擎。
- **不需要** pip install / 网络 —— `cli.py` 自举 `sys.path`(vendored `cadpy_metadata` 内联),
  刻意**不** vendor `requirements.txt`(不许往 uv 管理的 venv 里 pip 安装)。
- **不需要** `.cad_thread_pin` 线程钉定步骤 —— 那是 text-to-cad 容器跨线程共享 `/data` 的产物;
  本 CLI 直接在沙箱内读写**线程隔离**的 `/mnt/user-data`。

### 格式边界

- **URDF**(→ cad-urdf skill):物理结构——links、joints、几何、惯量、限位、mimic、transmissions。
- **SRDF**(本 skill):MoveIt 语义——virtual joints、passive joints、规划组、group states、
  末端执行器、禁撞对。
- **SDF**:仿真器/世界语义——物理、传感器、插件、世界。

绝不在 SRDF 里放:几何、惯量、joint origin、link pose、mesh 引用、物理限位、transmissions、
`ros2_control` 接口。

## 前置条件:一份合法的 .urdf(硬性)

SRDF 必须引用一份**已存在且合法**的 URDF。平台现状必须如实告知用户:

- `text-to-cad_create_step` / `inspect_step` / `search_step_parts` 是 **STEP-only**(vendored
  0.3.6 引擎没有 urdf/srdf CLI),**产不出 .urdf**。
- .urdf 的来源只有两条:① **cad-urdf skill**(`/app/skills/public/cad-urdf/`,同一上游、同样的
  纯 stdlib 本地 CLI 模式,**推荐配对使用**——先跑 URDF 工作流,再跑本 skill);② 用户直接
  上传/提供的 .urdf。
- 放置约定:generator 源码与 .urdf **都放在 `/mnt/user-data/` 下**;envelope 的 `urdf` 字段是
  **从 generator 源码指向 .urdf 的 POSIX 相对路径**(非绝对、正斜杠、`.urdf` 结尾、文件必须存在)。

## 强制工作流

1. **澄清规划任务**。记录目标:arm IK / 夹爪控制 / 移动底盘规划 / 双臂 / 工具使用 / 本地冒烟
   测试。仅当缺失信息使 SRDF 不可能写对(如不知道哪根 link 是 TCP)才问**一个**聚焦问题。

2. **拿到合法 URDF**(见前置条件)。先跑 cad-urdf 工作流或确认用户 .urdf 已在
   `/mnt/user-data/` 下;记住 URDF 的 robot name 与 link/joint 清单。

3. **写规划台账**。动笔写 XML 之前,先读 `references/planning-ledger.md` 建台账:每个规划组的
   依据、末端执行器的 parent/TCP link、组状态来源、禁撞对证据。

4. **写 `gen_srdf()` 源码**(Python,放 `/mnt/user-data/`,如 `/mnt/user-data/robot_semantic.py`):
   - **顶层零参函数 `def gen_srdf():`**,返回 envelope,**只允许两个字段**:
     ```python
     {"xml": <ET.Element 或 XML 字符串,根为 <robot name="...">>, "urdf": "robot.urdf"}
     ```
   - `urdf` = 从源码指向 .urdf 的 POSIX 相对路径。**不要**在 generator 里自己写 .srdf 文件
     (输出路径由 CLI 决定)。
   - ⚠️ CLI 直接 import generator 模块——**源码里的顶层代码会执行**,只对可信来源用本命令。
   - 语义元素模板(virtual_joint / group / chain / end_effector / group_state /
     disable_collisions 的完整示例)见 `references/generator-contract.md`。

5. **运行 CLI:校验通过才落盘**。生成器写好后:
   ```bash
   python3 /app/skills/public/srdf/scripts/srdf /mnt/user-data/robot_semantic.py \
       -o /mnt/user-data/outputs/robot.srdf
   ```
   (多目标用 `SOURCE.py=OUT.srdf` 对;`-o` 只能配恰好一个纯目标。)CLI 依次:import 源码 →
   调 `gen_srdf()` → 解析 URDF → 注入/更新 `tcad:urdf` 元数据 → 解析 SRDF → **对照 URDF 校验** →
   全部通过才写出文件并打印 `Wrote SRDF: ...`。输出必须放 `/mnt/user-data/outputs/` 下
   (present_files 才能拿到)。校验失败会抛错且**不写文件**——按错误信息修 generator,重跑。

6. **交付并如实汇报**。用 `present_files` 展示 `.srdf`。最终回复给 compact 校验报告
   (格式见 `references/validation.md`):跑过的检查、假设(TCP 假定、禁撞依据)、**跳过的检查**
   (MoveIt Setup Assistant / 采样碰撞矩阵 / MoveIt 冒烟——本部署全部不可用,必须如实写 skipped)。
   3D/交互查看:本平台**没有** SRDF/MoveIt 交互查看器(eai-flow-cad-viewer 只渲染 STEP/GLB),
   交接为 **report-only**——如实说明,不要假装给了查看链接。

## 常见陷阱(必读——校验器会精确抓住这些)

| 错误 ❌ | 正确 ✅ | 说明 |
|---------|--------|------|
| SRDF `<robot name>` 与 URDF 不一致 | **名字必须完全一致** | 校验器逐字比对,不一致直接 `SrdfSourceError` 拒写 |
| `group_state` 值写度数 | **revolute/continuous = 弧度,prismatic = 米**(URDF 原生单位) | 度数会触发 URDF 限位越界检查(如 90° > 1.57rad 上限)直接报错 |
| 末端执行器 group 与 parent_group 共享 link | **两者 link 集合不得重叠** | 重叠校验直接报错;parent_link 必须在 parent_group 内或与其 group 邻接 |
| `disable_collisions` 缺 reason / 编造宽泛禁撞表 | **每对都要真实 reason + 溯源**(adjacency/采样/Setup Assistant/用户数据) | 手工推断 ≥25 对会触发 warning;严禁模型自造大表 |
| 路径用反斜杠 `\\` 或绝对路径 | **POSIX `/` 相对路径**(输出 `.srdf` 结尾,envelope `urdf` `.urdf` 结尾) | CLI 显式拒绝反斜杠:`must use POSIX '/' separators` |
| `def gen_srdf(robot):` 带参数 / envelope 塞 `metadata` 等多余字段 | **零参,envelope 恰好 `{xml, urdf}`** | 带参或多字段 → TypeError 拒绝 |
| generator 里自己写 .srdf / 顶层跑副作用代码 | 输出交给 CLI;源码保持纯函数 + 顶层仅定义 | 顶层代码 import 即执行(安全边界);generator 写文件会绕过校验 |
| SRDF 里放 geometry/inertial/joint origin/mesh/限位 | 那些是 URDF 的;SRDF 只放语义 | 格式边界,见上 |
| 把校验通过当成规划正确 | 通过≠正确;chain 连通性/子组环/IK 可用性属浅层校验 | 按工作流第 6 步如实汇报 skipped 项 |

## 硬规则

- SRDF 必须引用已存在的合法 URDF;robot name 必须与 URDF 一致。
- group states 用 URDF 原生单位:revolute/continuous 弧度,prismatic 米。
- 禁撞对必须有真实 reason 与溯源;禁止编造宽泛禁撞表。
- 末端执行器 group 不与其 parent group 共享 link。
- 视觉审查有用,但**不能证明**规划正确。

## 工具

- `bash`(python3):唯一执行面。启动器 `/app/skills/public/srdf/scripts/srdf`(stdlib 自举,
  无 pip、无网络、无 text-to-cad 引擎)。
- `write_file` / `str_replace`:把 `gen_srdf()` 源码留档到 `/mnt/user-data/`。
- `read_file`:读用户 URDF、参考数据。
- `present_files`:展示 `/mnt/user-data/outputs/` 下的 `.srdf`。
- `ask_clarification`:缺关键信息时问。
- **明确不用**:`text-to-cad_create_step` / `text-to-cad_inspect_step` / `text-to-cad_search_step_parts`
  (本 skill 不产几何,也不进 text-to-cad 容器);**不需要** `.cad_thread_pin`。

## 深入参考(references/,上游原样保留)

- 生成命令细节:`references/gen-srdf.md`
- generator 契约(含完整语义元素示例):`references/generator-contract.md`
- SRDF 工作流全解:`references/srdf-workflow.md`
- 规划台账:`references/planning-ledger.md`
- 校验范围与报告格式:`references/validation.md`
- 末端执行器:`references/end-effectors.md`
- 禁撞对与证据规则:`references/disabled-collisions.md`
- 运行时形态与当前限制:`references/implementation-notes.md`

(注:references 内的 `python scripts/srdf ...` 为上游相对路径示例;本部署一律用上面的
绝对启动器路径。references 提到的 `$cad-viewer` / `moveit2_server` 在本部署不存在,见下。)

## 示例

用户:"给 sample_robot.urdf 配一个六轴臂规划组 + home 状态"(`sample_robot.urdf` 已由
cad-urdf skill 生成,位于 `/mnt/user-data/sample_robot.urdf`)

源码 `/mnt/user-data/sample_semantic.py`:
```python
import xml.etree.ElementTree as ET

def gen_srdf():
    robot = ET.Element("robot", {"name": "sample_robot"})   # 必须与 URDF name 一致
    arm = ET.SubElement(robot, "group", {"name": "manipulator"})
    ET.SubElement(arm, "chain", {"base_link": "base_link", "tip_link": "tool0"})
    home = ET.SubElement(robot, "group_state", {"name": "home", "group": "manipulator"})
    ET.SubElement(home, "joint", {"name": "shoulder_pan_joint", "value": "0.0"})  # 弧度!
    return {"xml": robot, "urdf": "sample_robot.urdf"}       # POSIX 相对路径
```
运行:
```bash
python3 /app/skills/public/srdf/scripts/srdf /mnt/user-data/sample_semantic.py \
    -o /mnt/user-data/outputs/sample_robot.srdf
```
成功输出 `Wrote SRDF: /mnt/user-data/outputs/sample_robot.srdf`(已注入
`<tcad:urdf path="../sample_robot.urdf"/>`)→ present_files → 写 compact 报告 → 结束。

## 当前状态(诚实标注)

本 skill 由 text-to-cad v0.3.6-era `skills/srdf` 原样 vendor(scripts/references 逐字节一致),
SKILL.md 按 EAI 模板重写。

**已实现**(生成时确定性校验):
- 显式目标生成:`gen_srdf()` → 校验通过才写 `.srdf`(校验门禁落盘)。
- SRDF-vs-URDF 校验:robot name 一致、规划组存在且非空、组内 joint/link/subgroup 存在、
  chain base/tip link 存在、group_state 归属组 + 有限值 + 禁 fixed/mimic + URDF 限位越界
  (限位可得时)、末端执行器重叠/邻接拓扑、禁撞对 link 有效性 + 去重 + 真实 reason。
- `tcad:urdf` 元数据注入/更新(兼容读 legacy `explorer:urdf`),`tcad:python-source` 溯源注释。
- 禁撞对溯源分桶(手工推断 ≥25 对触发 warning)。

**本部署不可用 / 降级**(必须向用户如实汇报,不得假装跑过):
- **MoveIt Setup Assistant 采样 / 采样自碰撞矩阵**:任何容器都没有 ROS/MoveIt2 → 相关工作流
  步骤永远 skipped。
- **MoveIt 冒烟测试 / moveit2_server / 交互式 IK·路径规划 review**:上游 `$cad-viewer` 的
  MoveIt2 控制在本平台不存在。
- **SRDF 交互查看器**:eai-flow-cad-viewer 只渲染 STEP/GLB,渲染不了 URDF/SRDF → 查看交接
  降级为 report-only。
- **virtual_joint / passive_joint 解析与校验**:上游 runtime 自认未完全实现(保留但不完整
  清点/校验)→ 需 MoveIt 侧人工核实。
- **浅层校验的边界**:URDF 全图一致性(重复 link/joint 可能被浅清单折叠)、chain base→tip
  连通性、子组环、每群组实际 IK 求解器可用性——这些生成时不做硬校验,依赖 cad-urdf 侧的
  URDF 校验 + 人工台账。
- **平台内 URDF 生产缺口**:text-to-cad MCP 工具 STEP-only,产不出 .urdf → 输入只能来自
  cad-urdf skill(推荐配对)或用户上传。

**运行环境事实**(已对 live 容器核实):gateway Python 3.12.14(要求 ≥3.11,用到 PEP 604
union 与 `ET.indent`),全部脚本 3.12 语法干净,`/app/skills` 为 host `skills/` 的 bind mount
(放入即见,无需镜像重建)。启用方式:`extensions_config.json` skills 块加 `"srdf": {"enabled": true}`(热加载)。
