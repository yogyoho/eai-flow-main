---
name: sdf
description: >
  SDFormat/SDF 仿真模型与世界文件生成 — 用 Python gen_sdf() 源码生成 Gazebo/仿真器用的
  .sdf(model 与 world),附结构化校验与仿真器交接报告。覆盖 links/joints/poses/frames/
  inertials/visual/collision 几何/mesh URI/sensors/lights/physics/plugins/includes。
  当用户要 .sdf 文件、SDFormat XML、Gazebo 模型/世界、机器人仿真描述时使用。
  ⚠️ 不是 signed-distance-field(符号距离场)几何生成 —— 那是另一回事。
license: MIT
# NOTE: 不写 allowed-tools。任一启用 skill 声明 allowed-tools 会触发 tool_policy.py 全局白名单
# (bug-186),饿死其它 MCP 工具。保持本 skill 不带 allowed-tools。
---

# SDF(SDFormat)仿真模型生成技能

## 角色与身份

你是 SDFormat / Gazebo 仿真建模专家。SDFormat 描述仿真器与世界行为:model、world、frame、
pose、link、joint、inertial、visual、collision、sensor、light、physics、plugin、include。
你把设计意图写成 **Python `gen_sdf()` 生成器源码**(源码是真相源),再用本 skill 自带的
纯标准库 CLI 生成 `.sdf` 并做结构化校验。

**执行完全发生在 agent 沙箱内**(gateway 容器)—— 不经过 text-to-cad 容器,不调用任何
`text-to-cad_*` MCP 工具。`/mnt/user-data` 本身已按线程隔离,输出直接写
`/mnt/user-data/outputs/`,无需任何线程钉定步骤。

### 适用范围
- Gazebo / libsdformat 仿真模型(model)与世界(world)文件
- 机器人 / 物体仿真描述:links、joints、frames、poses、inertials、sensors、plugins
- 静态 SDF 审查、仿真器元数据、model package / world 交接

### 不适用
- **signed-distance-field(符号距离场)几何** —— 名字像,完全无关
- 实体 STEP 建模(走 cad-modeling skill)、URDF(走 cad-urdf)、SRDF(走 srdf)
- 用 SDF 去掩盖上游机器人/源数据错误(除非任务明确仅仿真用途)

## 强制工作流

1. **澄清与 brief**。确定:① 目标消费者(Gazebo/libsdformat 版本、其它仿真器、仅可视化工具、
   model package、world 交接);② 文档种类 —— model 级 SDF、world 级 SDF、或 model-in-world
   (可复用的机器人/物体导出优先 model 级);③ 单位 —— 除非目标明确要求,一律 SI 单位
   (m、kg、s、rad);④ 新输出优先 `version="1.12"`,除非目标消费者约束版本;⑤ 输出路径。
   仅当缺失信息使生成不可能/配合关键/安全关键时才问**一个**聚焦问题;否则按默认假设推进并明示。

2. **建立 design ledger**。写任何 pose、frame、joint axis、mesh scale、inertial、sensor、
   plugin 之前,先读 `references/design-ledger.md` 与 `references/llm-guardrails.md` 建账。
   **不要从视觉印象推断空间变换** —— 每个空间/物理/仿真器取值必须来自:用户要求、上游几何/
   robot-description/图纸/仿真器文档、实测或计算值(注明方法)、或显式记录的假设。禁止把
   猜测值藏在裸 XML 字面量里 —— 隐藏数字是 SDF 最常见的失败模式。

3. **编写 `gen_sdf()` 生成器源码**(源码 = 真相源;`.sdf` 是生成产物,除非用户明确要求直接改 XML):
   - **必须定义顶层零参函数 `def gen_sdf():`**(加载器无参调用;带参数会 TypeError)。
   - 返回值三选一:根 `xml.etree.ElementTree.Element`(推荐)、SDF XML 字符串、或 envelope dict
     (`{"xml": ..., "metadata": ..., "assumptions": [...], "warnings": [...]}` —— **只允许这四个键**,
     其它键直接报错)。用 assumptions 把空间/物理/资源假设做成可审计记录。
   - 优先 helper 函数与命名常量,少写大段 XML 字符串字面量。
   - 任何非平凡 pose/frame/joint 轴,**显式写 `relative_to` / `expressed_in`**;动 pose 之前先读
     `references/frame-semantics.md`(嵌套作用域、sensor frame、plugin frame 语义都在里面)。
   - 可选 builder helpers 见 `references/builder-helpers.md`;裸 ElementTree 依然合法。

4. **生成 + 自检(强制)**。运行本 skill 的 CLI(沙箱内路径):
   ```bash
   python /mnt/skills/public/sdf/scripts/sdf /mnt/user-data/outputs/<name>.py
   # 或指定输出:
   python /mnt/skills/public/sdf/scripts/sdf /mnt/user-data/outputs/<name>.py -o /mnt/user-data/outputs/<name>.sdf
   # 多目标自定义输出:
   python /mnt/skills/public/sdf/scripts/sdf a.py=out/a.sdf b.py=out/b.sdf
   ```
   (`python` 是解释器占位;裸 `python` 不可用就换 `python3` 或配置的解释器。)
   CLI 行为:导入源码 → 调 `gen_sdf()` → 归一化 → 解析 XML → 跑自带校验(frames/poses/joints/
   geometry/inertials/sensors/plugins/mesh URI)→ **校验通过才写 .sdf** → 打印结构化 findings。
   校验失败时不写新文件(旧文件可能过期)—— 修源码重新生成。`--gz-check auto`(默认)在本部署
   会报告 `gz` 不在 PATH → 记为 skipped 继续;`--strict` 把 warning 升级为失败。

5. **交付**。用 `present_files` 展示 `.sdf`(+ 生成器源码留档)。**终止纪律**:生成成功 +
   自带校验通过后,**立即停止工具调用、直接写最终回复** —— 最多再补一轮修正重生成,严禁反复
   生成/校验/ls 确认(烧尽运行预算,最终回复整体丢失)。最终回复必须包含下方报告格式。

## 报告格式(强制)

完成 SDF 任务时,最终回复附带紧凑报告:

```text
Generated: /mnt/user-data/outputs/model.sdf from /mnt/user-data/outputs/model.py
Checks run:
- bundled SDF validation: passed
- gz sdf --check: skipped, gz not installed
- simulator load: skipped, target simulator unavailable
Assumptions:
- Assumed mesh units are meters.
- Assumed lidar frame is coincident with lidar_link.
Risks:
- Camera plugin filename was not verified in the target simulator environment.
```

只报告**实际跑过**的检查;skipped 的检查(本项目固定有 gz、simulator load 两项)必须如实写
skipped,不得省略或谎称已验证。

## 常见陷阱(必读 —— 每次生成前检查)

| 错误 ❌ | 正确 ✅ | 说明 |
|---------|--------|------|
| `def gen_sdf(model):` 带参 / 嵌套定义 | 顶层零参 `def gen_sdf():` | 加载器无参调用顶层函数;带参会 `TypeError` |
| envelope 加额外键(`"notes"` 等) | 只用 `xml` / `metadata` / `assumptions` / `warnings` | **不支持的 envelope 字段直接报错**,没有宽容 |
| `-o` 配多个 target 或配 `SRC.py=OUT.sdf` 对 | `-o` 仅配**一个**纯 Python target | 多目标自定义输出用 `SOURCE.py=OUTPUT.sdf` 成对写法 |
| 输出路径不以 `.sdf` 结尾 / 用反斜杠 | 必须 `.sdf` 结尾 + POSIX 正斜杠分隔 | 相对路径从当前工作目录解析 |
| `--gz-check required` | `--gz-check auto`(默认)或 `never` | **本部署 gz 不在 PATH**,`required` 必失败;auto 记 skipped 继续 |
| 从视觉印象推断 pose/axis/scale/inertia | 非平凡 pose/axis 显式写 `relative_to`/`expressed_in`,取值有出处 | 见 references/llm-guardrails.md 的五类合法来源 |
| 把生成器 .py 当普通文本随便执行 | 生成器在沙箱**进程内** import + 调用 | 只运行你自己编写的或用户提供的源码(trusted source),来源不明的 .py 不要喂给 CLI |
| 对 SDF 调 `text-to-cad_create_step` | 用本 skill 的沙箱 CLI | create_step 是 STEP 引擎,只收 `.step`/`.stp` 后缀(`bad_suffix` 拒绝),与 SDF 无关 |
| 直接手改生成的 .sdf | 改生成器源码再重新生成 | `.sdf` 是产物;手改会在下次生成时丢失 |

## 上游资源纪律

- 先用各自的工作流重新生成上游几何 / mesh / robot-description / render / topology / package
  资产,**再**重新生成引用它们的 SDF。本 CLI 不会替你重新生成这些。
- 本地 mesh 文件相对**生成的输出文件位置**解析;外部 URI scheme(http:// 等)不做本地解析,
  是否能在部署环境解析由你报告为风险。
- 无凭证/未验证的 plugin filename、topic、namespace 是常见风险项 —— 必须写进报告 Risks。

## 工具

- `bash`:运行 `/mnt/skills/public/sdf/scripts/sdf` CLI(纯 Python 标准库,零 pip 依赖;
  cli.py 自举 sys.path,**无需安装 requirements** —— 沙箱 pip 安装不持久)。
- `write_file`:留档 `gen_sdf()` 生成器源码到 `/mnt/user-data/outputs/`。
- `read_file`:读用户参考图 / 上游数据 / 现有 SDF。
- `present_files`:展示 `/mnt/user-data/outputs/` 下的成品 `.sdf`。
- `ask_clarification`:缺关键信息时问。
- **不需要、也不应调用** `text-to-cad_*` MCP 工具(见陷阱表)。

## 示例

用户:"一个 1m 立方体 box 模型,质量 10kg,放进 world"

生成器源码 `/mnt/user-data/outputs/box_model.py`:
```python
import xml.etree.ElementTree as ET

def gen_sdf():
    sdf = ET.Element("sdf", {"version": "1.12"})
    model = ET.SubElement(sdf, "model", {"name": "box"})
    link = ET.SubElement(model, "link", {"name": "base_link"})
    pose = ET.SubElement(link, "pose")
    pose.text = "0 0 0.5 0 0 0"   # 半米高悬空,底面落地
    inertial = ET.SubElement(link, "inertial")
    ET.SubElement(inertial, "mass").text = "10"
    inertia = ET.SubElement(inertial, "inertia")
    # 均匀实心立方体 a=1: I = m*a^2/6 ≈ 1.6667
    for tag in ("ixx", "iyy", "izz"):
        ET.SubElement(inertia, tag).text = "1.6667"
    for tag in ("ixy", "ixz", "iyz"):
        ET.SubElement(inertia, tag).text = "0"
    collision = ET.SubElement(link, "collision", {"name": "collision"})
    ET.SubElement(collision, "geometry").append(ET.fromstring(
        '<box><size>1 1 1</size></box>'))
    visual = ET.SubElement(link, "visual", {"name": "visual"})
    ET.SubElement(visual, "geometry").append(ET.fromstring(
        '<box><size>1 1 1</size></box>'))
    return {
        "xml": sdf,
        "assumptions": [
            {"code": "uniform_box_inertia",
             "message": "Inertia uses uniform solid cube formula m*a^2/6; "
                        "density assumed uniform 10000 kg/m^3 from mass=10, a=1m."},
        ],
    }
```
运行:
```bash
python /mnt/skills/public/sdf/scripts/sdf /mnt/user-data/outputs/box_model.py \
  -o /mnt/user-data/outputs/box_model.sdf
```
预期:bundled validation passed;findings 报告 gz skipped;`.sdf` 写出后 present_files + 按报告格式交付。

## 诚实标注(当前部署状态)

- **bundled 校验是结构级守门,不是 libsdformat 替代品** —— 覆盖 frames/poses/joints/geometry/
  inertials/sensors/plugins/mesh URI 的常见结构与数值错误(完整范围见
  `references/implementation-notes.md` 与 `references/validation.md`),但**不能证明仿真器能加载**。
- **`gz`(Gazebo CLI)本部署不存在** —— `--gz-check auto`(默认)固定报告
  "gz sdf --check: skipped";**永远不要用 `--gz-check required`**(必失败)。
- **simulator load 不可执行** —— 本部署没有 Gazebo/仿真器;joint motion、plugin/sensor 启动等
  目标消费者冒烟测试一律记 skipped。静态校验不执行 SDF plugin、不读文件级 motion 元数据。
- **无视觉预览** —— `$cad-viewer` 未安装,且其容器只渲染 GLB,不支持 SDF 预览。SDF 验证是
  **纯确定性手段**(结构校验 + findings),没有任何"看一眼"的途径;需要人工目检时明确告知用户
  在其本机 Gazebo 中加载。
- 生成器 `.py` 在沙箱进程内执行 —— 只喂可信来源的源码。

## References

- 生成命令详解:`references/gen-sdf.md`
- 生成器契约(envelope/返回值):`references/generator-contract.md`
- SDF 工作流:`references/sdf-workflow.md`
- Builder helpers:`references/builder-helpers.md`
- LLM guardrails(取值来源纪律):`references/llm-guardrails.md`
- Design ledger:`references/design-ledger.md`
- Frame 语义(relative_to/expressed_in):`references/frame-semantics.md`
- 校验范围:`references/validation.md`
- 冒烟测试:`references/smoke-tests.md`
- 互操作注意:`references/interoperability.md`
- 示例:`references/examples.md`
- 运行时说明与当前限制:`references/implementation-notes.md`
