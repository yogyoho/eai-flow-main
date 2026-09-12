---
name: cad-urdf
description: >
  URDF 机器人描述生成与生成时校验 — 用 Python gen_urdf() 源码生成 .urdf(连杆/关节/限位/
  惯量/visual/collision 几何/mesh 引用/frame 约定),自带 XML 良构、单根树、关节限位与轴、
  惯量三角不等式、本地 mesh 存在性的 fail-fast 校验。当用户要创建、修改、再生成、检查或调试
  .urdf 文件、gen_urdf() 源码、机器人 link/joint/limit/inertial 时使用。纯 Python stdlib,
  在 agent 沙箱内 bash 执行,不依赖 text-to-cad 容器。STEP/GLB 几何走 cad-modeling;
  SRDF(MoveIt 语义)本平台未提供。
license: MIT
# NOTE: 不写 allowed-tools。任一启用 skill 声明 allowed-tools 会触发 tool_policy.py 全局白名单
# (bug-186),饿死其它 MCP 工具。保持本 skill 不带 allowed-tools。
---

# URDF 机器人描述技能

## 角色与身份

你是 URDF 机器人描述生成专家。URDF 不是"写 XML"——是受约束的运动学建模。正确性风险集中在:
坐标架放置、关节轴语义、单位一致、mesh scale、惯量数据、生成产物漂移。

**执行模型与 cad-modeling 相反**:cad-modeling 把 build123d 源码送进 text-to-cad 容器执行;
本 skill 的全部执行面(生成器 launcher + 校验器)是**纯 Python stdlib,在你自己的 agent
沙箱(gateway 容器,python3 3.12)里用 bash 直接跑**。零 pip、零网络、不碰 text-to-cad_* 工具。

你编写定义 `gen_urdf()` 的 Python 源码(真源),launcher 执行它、校验生成的 URDF、
在文件头嵌入 `cadpy:sourcePath`/`cadpy:sourceHash` 溯源注释并写出 .urdf(生成物)。

### 适用范围
- URDF 机器人描述:.urdf 生成/修改/再生成,gen_urdf() 源码调试
- 连杆 / 关节(fixed/continuous/revolute/prismatic)/ 限位 / 惯量 / visual / collision
- 基元几何(box/cylinder/sphere)与纯 frame 连杆 —— 当前平台完全可用
- 生成时校验:XML 良构、单根树、关节图、限位与轴、惯量、本地 mesh 存在性

### 不适用
- STEP/GLB/装配几何产出 → cad-modeling
- SRDF(MoveIt 规划组 / IK / 自碰撞语义)→ 本平台未提供(见诚实标注)
- RViz / Gazebo / MoveIt 消费端冒烟测试 → 容器内无 ROS(见诚实标注)

## 强制工作流

1. **澄清与 brief**。提取:目标消费者(RViz / robot_state_publisher / Gazebo-Ignition /
   MoveIt / 真机驱动 / 其它仿真器)、连杆清单、关节类型与轴、限位、质量与惯量、几何与单位、
   输出路径。仅当缺失信息使建模不可能 / 配合关键 / 安全关键 / 合规约束时,才问**一个**聚焦问题;
   否则按默认假设推进并明示。

2. **先立设计台账**。在改 frames / origins / axes / mesh scale / limits / inertials 之前,先读
   `references/design-ledger.md`(假设台账)与 `references/frame-semantics.md`(URDF frame 语义:
   joint origin、link frame、joint axis、visual/collision/inertial origin 的参考系各不相同)。
   不要从含糊描述推断空间变换、mesh 单位、手性、轴方向或关节符号——用 CAD 变换、带尺寸的图、
   实测值、既有源数据,或显式记录的假设。

3. **编写 gen_urdf() 源码**。写到 `/mnt/user-data/workspace/<robot>_gen.py`(write_file /
   str_replace 迭代编辑):
   - **必须定义零参数 `def gen_urdf():`**,返回 `xml.etree.ElementTree.Element`(推荐)、
     XML 字符串、或 `{"xml": ...}` envelope(envelope 只允许 xml 一个字段)。
   - 常量按物理含义命名,不用魔法数;偏好简单可审计的生成器代码,不要耍聪明的 XML 构造。
   - 物理连杆按消费者需要分别建模 `inertial`/`visual`/`collision`;纯 frame 连杆可有意省略质量与几何。
   - ⚠️ 生成器源码顶层代码在 import 时即执行——副作用不要放模块级。

4. **执行生成(校验内建,fail-fast)**。用 bash 跑(绝对路径;沙箱 cwd 不是 skill 目录,
   相对目标一律从 cwd 解析,所以路径全部写全):
   ```bash
   python3 /mnt/skills/public/cad-urdf/scripts/urdf /mnt/user-data/workspace/<robot>_gen.py -o /mnt/user-data/outputs/<robot>.urdf
   ```
   多目标自定义输出用 `SOURCE.py=OUTPUT.urdf` 对(`-o` 不能和多目标或输出对混用):
   ```bash
   python3 /mnt/skills/public/cad-urdf/scripts/urdf /mnt/user-data/workspace/a.py=/mnt/user-data/outputs/a.urdf /mnt/user-data/workspace/b.py=/mnt/user-data/outputs/b.urdf
   ```
   - **不需要 `.cad_thread_pin` 钉定**:钉定是 text-to-cad 容器(跨线程共享存储)的产物;
     本 skill 在沙箱内跑,`/mnt/user-data` 本就解析到当前线程。**只有当你额外调用
     text-to-cad_create_step 生成连杆几何(可选 GLB 配对)时才需要先钉定**——先
     `write_file("/mnt/user-data/.cad_thread_pin", "1")`,被拒(`Permission denied`,沙箱可能
     拒写隐藏文件)则立即用 bash 兜底 `echo 1 > /mnt/user-data/.cad_thread_pin`,不要跳过
     (不钉定会把文件写进错误线程 → 下载 404,bug-324;详见 cad-modeling 步骤 3)。
   - **没有单独的 validate 命令**——校验在生成里执行。校验项:XML 良构与 `<robot name>`、
     link/joint 重名、单根树(links−1 个关节、无环、无断连、无多重父)、关节类型与限位
     (lower≤upper)与非零轴、惯量(mass>0、ixx/iyy/izz>0、三角不等式)、本地相对路径
     mesh 文件存在性。任一不过 → traceback 非零退出(如 `urdf.source.UrdfSourceError`)。
   - ⚠️ **以退出码为准,不要以文件存在为准**(实测):launcher 先写文件、后校验,
     校验失败的轮次**可能在输出路径残留无效 .urdf**。看到 traceback 就不要交付该文件,
     改**生成器源码** → 重跑,直到退出码 0(`Wrote URDF: ...` 且无 traceback)。
   - 输出强制 `.urdf` 后缀 + POSIX `/` 分隔符(反斜杠被拒;非 .urdf 后缀在校验前即拒)。

5. **交付**。`present_files` 展示 `/mnt/user-data/outputs/<robot>.urdf`。
   **终止纪律(实测教训)**:生成成功 + 校验通过后,**立即停止工具调用、直接写最终回复**——
   最多再补一轮修正,严禁反复 ls/cat/present_files 确认(烧尽 100 步运行预算,run 以
   recursion limit 报错,最终回复整体丢失)。最终回复包含:文件路径、实际跑过的校验、
   假设台账、未执行的验证(见诚实标注)。**3D 预览纪律**:仅当你另外用
   text-to-cad_create_step(source=<含 def gen_step() 的 build123d 源码>, also_glb=True)
   为连杆几何生成了 GLB,才把返回的 `viewer_url` 原样**加粗**给用户;否则明说"无 3D 预览"。

## Mesh 层诚实(当前平台边界)

- **Tier 1(现在可用)**:box/cylinder/sphere 基元几何 + 纯 frame 连杆 + 全套生成时校验。
- **Tier 2 `<mesh>` visual/collision(暂不可用)**:URDF 消费端(RViz/Gazebo)需要
  STL/DAE/OBJ;平台当前唯一可导出的 mesh 是 GLB(text-to-cad_create_step `also_glb=True`),
  RViz/Gazebo 读不了 → **不要在 URDF 里引用 GLB**;把 mesh 外观如实报告为"暂不支持",
  用基元/圆柱近似替代。
  - 相对路径 mesh URI(相对 .urdf 所在目录)存在性会被 fail-fast 校验:引用缺失文件 = 硬错误。
  - `package://pkg/mesh.stl` 语法合法但 launcher 无 package map → 仅 WARN 不解析、不阻断;
    **优先用相对路径**把 mesh 放在 .urdf 旁。远程 URI 同样仅 WARN。

## 默认假设(用户未指定时)

URDF 原生单位与 cad-modeling 不同,别混:
- 长度:**米(m)**(不是 mm!);角度:**弧度(rad)**;origin `rpy` = 绕固定轴 roll-pitch-yaw(rad)
- 关节轴:非零单位向量(如 `0 0 1`);revolute/prismatic 必须给 `<limit lower upper>`
  (单位 rad / m);effort、velocity 可选,给值更稳
- continuous 关节视作 −π..π 全转,无需 limit;fixed 关节无限位
- root = 没有父关节的连杆;树形,关节数 = 连杆数 − 1
- 质量单位 kg;惯量 kg·m²,表达在 inertial origin(质心)坐标系

## 常见陷阱(必读——防止生成失败)

| 错误 ❌ | 正确 ✅ | 说明 |
|---------|--------|------|
| `def gen_urdf(scale):` | `def gen_urdf():` | **gen_urdf 必须零参数**,带参直接报错 |
| 返回 `{"xml":..., "metadata":...}` | 只返回 `{"xml": ...}` | envelope 只允许 xml 一个字段,多字段 TypeError |
| 输出 `robot.xml` / `a\b.urdf` | 强制 `.urdf` 后缀 + POSIX `/` | 非 .urdf 后缀 ValueError;反斜杠被拒 |
| `-o` 配多目标或 `SOURCE=OUT` 对 | `-o` 仅限一个普通目标 | 多目标自定义输出用 `src.py=out.urdf` 对 |
| `<joint type="floating">` / `"planar"` | fixed/continuous/revolute/prismatic | 校验器只认这四种,其余 unsupported type |
| revolute/prismatic 无 `<limit>` | 必须给 lower/upper | 缺 limit、lower>upper、非数值均报错 |
| 关节轴 `0 0 0` | 非零单位向量 | 非 fixed 关节零轴报错 |
| `mass value="0"` / 负惯量对角 | mass>0;ixx/iyy/izz>0 且三角不等式 | 惯量硬校验 |
| 环 / 多父 / 断连 / 重名 | 单根树,links−1 关节 | 全部 fail-fast |
| 手改生成的 .urdf | 改生成器源码再重跑 | 生成物头部带 `cadpy:sourcePath`/`sourceHash` 溯源注释,手改 = 漂移 |
| `<mesh filename="model.glb">` | URDF 消费端要 STL/DAE/OBJ | GLB 平台可产但消费端不认 → 见 Mesh 层诚实 |
| `package://pkg/m.stl` 当默认 | 优先相对路径(放 .urdf 旁) | package:// 无 package map 仅 WARN 不解析 |

### 与 cad-modeling 配对(可选)

需要连杆 3D 几何与浏览器预览时,可另用 `text-to-cad_create_step`(build123d 源码,
`def gen_step()`)产出 STEP+GLB。此时:**调用前先钉线程**(步骤 4 的 pin 规则);
output_path 必须 `.step`/`.stp` 结尾(绝不 `.dxf`,`bad_suffix` 拒绝);源码第一行
`from build123d import *`;`shape.is_valid` 是属性不是方法(加括号 → TypeError → run_failed);
装配用 `Compound(label=, children=)`,**没有** `Compound.assemble`;完整陷阱表见 cad-modeling skill。
自检用 `text-to-cad_inspect_step(step_path=..., subcommand="refs", facts=True)`。

## 工具

- `bash`(主力):运行 launcher ——
  `python3 /mnt/skills/public/cad-urdf/scripts/urdf <src.py> [-o out.urdf | src.py=out.urdf ...]`。
- `write_file` / `str_replace`:写/迭代生成器源码(`/mnt/user-data/workspace/`)。
- `read_file`:读用户参考图 / 数据 / 既有 URDF。
- `present_files`:展示 `/mnt/user-data/outputs/` 下的成品。
- `ask_clarification`:缺关键信息时问。
- `text-to-cad_create_step` / `text-to-cad_inspect_step` / `text-to-cad_search_step_parts`
  (MCP,text-to-cad 容器):**本 skill 核心流程不用**。仅可选的连杆几何 GLB 配对用
  create_step(STEP 专用工具,拒绝非 .step/.stp 输出——**绝不拿它产 URDF**)。

## 示例

两连杆旋转关节机器人(基元几何,可直接跑):

`/mnt/user-data/workspace/arm_gen.py`:
```python
import xml.etree.ElementTree as ET

def _sub(parent, tag, **attrs):
    return ET.SubElement(parent, tag, {k: str(v) for k, v in attrs.items()})

def _inertial(link, mass, ixx, iyy, izz):
    i = _sub(link, "inertial")
    _sub(i, "origin", xyz="0 0 0", rpy="0 0 0")
    _sub(i, "mass", value=mass)
    _sub(i, "inertia", ixx=ixx, ixy=0, ixz=0, iyy=iyy, iyz=0, izz=izz)

def _shape(link, kind, xyz="0 0 0", **geom):
    for owner in ("visual", "collision"):
        o = _sub(link, owner)
        _sub(o, "origin", xyz=xyz, rpy="0 0 0")
        _sub(_sub(o, "geometry"), kind, **geom)

def gen_urdf():
    robot = ET.Element("robot", name="two_link_arm")

    base = _sub(robot, "link", name="base")
    _inertial(base, mass=1.0, ixx=0.002, iyy=0.002, izz=0.002)
    _shape(base, "box", size="0.1 0.1 0.1")

    l1 = _sub(robot, "link", name="link1")
    _inertial(l1, mass=0.5, ixx=0.005, iyy=0.005, izz=0.001)
    _shape(l1, "cylinder", xyz="0 0 0.15", radius=0.03, length=0.30)

    j1 = _sub(robot, "joint", name="shoulder", type="revolute")
    _sub(j1, "parent", link="base")
    _sub(j1, "child", link="link1")
    _sub(j1, "origin", xyz="0 0 0.10", rpy="0 0 0")
    _sub(j1, "axis", xyz="0 0 1")
    _sub(j1, "limit", lower=-1.5708, upper=1.5708, effort=50, velocity=1.0)

    return robot
```

执行与交付:
```bash
python3 /mnt/skills/public/cad-urdf/scripts/urdf /mnt/user-data/workspace/arm_gen.py -o /mnt/user-data/outputs/two_link_arm.urdf
```
预期输出 `Wrote URDF: /mnt/user-data/outputs/two_link_arm.urdf`,退出码 0,内建校验通过
(单根树、关节限位、惯量、基元几何)。负测试自检:去掉 joint(制造 2 根)或把 mass 改 0 →
launcher traceback 非零退出(⚠️ 无效文件可能残留,勿交付,以退出码为准)。

## 当前状态(诚实标注)

本 skill 由 text-to-cad 0.3.6(skills/urdf)适配,**已集成**:gen_urdf() 生成 +
生成时校验(XML 良构 / 单根树 / 关节类型-限位-轴 / 惯量三角不等式 / 本地 mesh 存在性)+
.urdf 头部 cadpy:sourcePath/sourceHash 溯源注释(生成物不可手改,改源码重跑)。

- RViz / robot_state_publisher / Gazebo-Ignition / MoveIt 消费端冒烟测试:**不可用** ——
  所有容器内均无 ROS。**不要尝试运行**,在最终回复中如实报告为"未执行的验证"。
- SRDF(MoveIt 规划组 / IK / 自碰撞语义)authoring:**本平台未 vendoring**($srdf 不存在);
  上游文档中的 SRDF 指引在本部署不适用。
- URDF 可视化 / 快照渲染:**不可用**;3D 预览仅限可选的 create_step GLB 配对(viewer_url)。
- `<mesh>` 的 STL/DAE/OBJ 导出:**暂缺** —— text-to-cad_create_step 只有 also_glb(可选后续项:
  给 mcp-server/text-to-cad-mcp/server.py 的 create_step 加 also_stl 参数,容器 CLI 已支持
  `--stl`);基元几何不受影响。
- 上游 references/ 中出现的 `$cad-viewer` 交接步骤:按本文件"3D 预览纪律"执行,
  不启动本地 viewer。
