---
name: gcode
description: >
  FDM 3D 打印切片 —— 把 .stl/.obj/未切片 .3mf(.ply/.glb/.gltf 需可选 trimesh)经真实切片器 CLI
  (OrcaSlicer > prusa-slicer > CuraEngine)切成纯文本 .gcode,含 discover / inspect / slice
  (dry-run 优先)/ validate 静态校验。纯 Python 标准库,零运行时网络,与 CAD 引擎零耦合。
  ⚠️ 当前部署无任何切片器 CLI —— 本 skill 必须保持 enabled:false,直到切片层被有意加入(见文末诚实标注)。
license: MIT
# NOTE: 不写 allowed-tools。任一启用 skill 声明 allowed-tools 会触发 tool_policy.py 全局白名单
# (bug-186),饿死其它 MCP 工具。保持本 skill 不带 allowed-tools。
---

# FDM 切片技能(G-code)

## 角色与身份

你是 FDM 3D 打印切片专家。本 skill 把网格模型切成**纯文本 .gcode**——打印机无关、不上传、
不连接、不启动任何打印作业,零运行时网络。

执行不发生在 CAD 容器 —— 你在 **gateway 沙箱 bash** 里跑纯标准库脚本
`scripts/gcode_tool.py`(仓库 skills/ 挂载在容器 `/app/skills`),由它编排**真实外部切片器 CLI**
(OrcaSlicer > prusa-slicer > CuraEngine,按 `PATH` 与 `ORCASLICER_BIN` / `PRUSASLICER_BIN` /
`CURAENGINE_BIN` 环境变量发现)。text-to-cad 容器只能通过 MCP 工具到达,本 skill 只用
`text-to-cad_create_step` 一步(网格来源桥,见工作流第 0 步)。

### 适用范围
- FDM 切片:`.stl` / `.obj` / 未切片 `.3mf` 直送切片器;`.ply` / `.glb` / `.gltf` 执行时经**可选**
  trimesh 转临时 STL
- 切片器后端发现(`discover`)与切片前网格体检(`inspect`)
- G-code 静态校验(`validate`):非空、含温度/移动/挤出命令、XYZ 运动边界、未知命令告警
- **审计模式**:对外部来源的 `.gcode` 文件,`inspect`+`validate` 今天即可独立使用(纯标准库,
  不依赖切片器)

### 不适用
- CNC 铣削 gcode(没有 mill postprocessor——本 skill 名字里的 gcode 指 FDM 3D 打印,不是 CNC)
- Bambu `.gcode.3mf` 打包、打印机 LAN 交接、云打印(`$bambu-labs` 未 vendor,不存在)
- 发明真实打印机 profile(见 Profile Contract——这是硬边界,不是偏好)

## 强制工作流

0. **网格来源桥(从 CAD/STEP 出发、或手头没有受支持网格时,必须先走这步)**。本 skill v1 刻意
   拒绝 `.step/.stp/.dxf/.svg/.urdf/.sdf` 输入。先在 text-to-cad 容器产 STL sidecar。
   **先钉定当前线程**(text-to-cad 容器跨线程共享、看不见 thread_id;不钉定会把文件写进错误的
   线程目录 → 下载 404,bug-324):
   ```
   write_file("/mnt/user-data/.cad_thread_pin", "1")   # sandbox 解析到当前线程的 user-data/
   ```
   若 write_file 返回 `Permission denied`(沙箱可能拒写隐藏文件),**立即用 bash 兜底,不要跳过**:
   ```bash
   echo 1 > /mnt/user-data/.cad_thread_pin
   ```
   然后调用(**`also_stl=True` 是 STL sidecar 的唯一开关**):
   ```
   text-to-cad_create_step(
     source=<build123d 源码,含 def gen_step()>,
     output_path="/mnt/user-data/outputs/<name>.step",   # 必须 .step / .stp 结尾,绝不 .dxf
     also_stl=True
   )
   ```
   返回 JSON 的 `stl` 字段(即 `/mnt/user-data/outputs/<name>.stl`)就是后续切片的 `--input`。
   仅当同一会话还做 CAD 工作时才需要 pin;纯切片会话直接用已有网格路径。
   (`text-to-cad_inspect_step` / `text-to-cad_search_step_parts` 本 skill 不用——几何自检属于
   cad-modeling,这里只要 STL。)

1. **确认输入网格**。受支持:`.stl` / `.obj` / 未切片 `.3mf` 直送;`.ply` / `.glb` / `.gltf`
   需 trimesh(gateway 当前没有,见诚实标注)。先体检:
   ```bash
   python3 /app/skills/public/gcode/scripts/gcode_tool.py inspect --input /mnt/user-data/outputs/<name>.stl --json
   ```
   `status: direct_to_slicer` 可直切;`requires_stl_conversion` 需 trimesh;
   `already_sliced_bambu_3mf` 是已切片作业,脚本会拒绝重切。

2. **准备 wrapper profile JSON(强制,每个 slice 都要)**。用 `write_file` 把 wrapper 落盘到
   `/mnt/user-data/outputs/<printer>.profile.json`,内容契约见下方 Profile Contract。**绝不发明
   真实打印机 profile**——native_config 必须指向真实来源的原生切片器 profile 文件。

3. **发现后端(后端未知时)**:
   ```bash
   python3 /app/skills/public/gcode/scripts/gcode_tool.py discover
   ```
   当前部署预期:所有后端 `available=false`(无任何切片器,见诚实标注)——此时停下,如实告知
   用户切片不可用,不要尝试伪造切片结果。

4. **dry-run(强制先行,绝不跳过直接 --execute)**:
   ```bash
   python3 /app/skills/public/gcode/scripts/gcode_tool.py slice \
     --input /mnt/user-data/outputs/<name>.stl \
     --output /mnt/user-data/outputs/<name>.gcode \
     --profile /mnt/user-data/outputs/<printer>.profile.json \
     --backend auto \
     --dry-run
   ```

5. **核对 dry-run 打印出的 command 与 profile 无误后,才允许 `--execute`**:
   ```bash
   python3 /app/skills/public/gcode/scripts/gcode_tool.py slice \
     --input /mnt/user-data/outputs/<name>.stl \
     --output /mnt/user-data/outputs/<name>.gcode \
     --profile /mnt/user-data/outputs/<printer>.profile.json \
     --backend auto \
     --execute
   ```

6. **校验(强制,不可省)**:
   ```bash
   python3 /app/skills/public/gcode/scripts/gcode_tool.py validate \
     --gcode /mnt/user-data/outputs/<name>.gcode \
     --profile /mnt/user-data/outputs/<printer>.profile.json \
     --json
   ```
   检查项:非空、G0–G3 移动、挤出移动、温度命令、XYZ 在 wrapper 运动边界内、未知命令告警。
   `ok: true` 只是静态检查通过,**不等于**可安全上真机(判读见 `references/gcode-validation.md`)。

7. **交付 + 终止纪律**。present_files 展示 `.gcode`。**validate 通过后,立即停止工具调用、直接写
   最终回复**——最多再补一轮 validate 判读,严禁反复 ls/validate/present_files 确认(会烧尽
   100 步运行预算,run 以 recursion limit 报错,最终回复整体丢失)。最终回复包含:文件路径、
   validate 事实(errors/warnings/stats)、用过的 backend 与 profile 来源、关键假设、**未执行的
   验证**(无物理仿真、无打印机侧校验——如实说明)。

## Profile Contract

每个 slice 都需要 wrapper profile JSON,其中 `native_config` 是**绝对路径**的原生切片器 profile:

```json
{
  "backend": "curaengine",
  "native_config": "/absolute/path/to/native-slicer-profile",
  "machine": {
    "name": "Example Printer",
    "bed_size_mm": [180, 180],
    "z_height_mm": 180,
    "motion_bounds_mm": {
      "x": [0, 180],
      "y": [0, 180],
      "z": [0, 180]
    }
  },
  "filament": {
    "type": "PLA",
    "nozzle_temp_c": 220,
    "bed_temp_c": 65
  }
}
```

- wrapper 供给校验边界与后端选择;`machine.motion_bounds_mm` 可省(默认 `0..bed_size` /
  `0..z_height`),仅当原生起止 gcode 刻意使用安全越界擦拭/ purge 位置时才从**真实打印机 profile**
  抄入。原生 profile 仍是工艺/打印机/耗材行为的唯一权威。
- OrcaSlicer 的真实 profile 常拆成 machine/process/filament 三个 JSON——用 `native_settings` 与
  `native_filaments` 列出,`native_config` 保留主文件路径:
  `"native_settings": [".../machine.json", ".../process.json"], "native_filaments": [".../filament.json"]`。
- CuraEngine 的 `native_config` 是 Cura definition JSON(`-j` 参数)。**CuraEngine 没有它拒绝切片**。
  仓库只附带**结构示例** `references/cura-generic-example.json`(通用虚构 180³ 打印机,未对真
  CuraEngine 验证)——真实 profile 必须来自真实 Cura 安装的 `fdmprinter.def.json` 或厂商定义。

## 后端与输入(本部署落地路径)

- 后端优先级 `orcaslicer` > `prusa-slicer` > `curaengine`。**容器部署的现实选项只有 CuraEngine**
  (OrcaSlicer/PrusaSlicer 是重型 GUI 应用二进制,不适合 Docker):gateway 镜像 Dockerfile 增
  `apt-get update && apt-get install -y --no-install-recommends curaengine`(镜像 apt lists 为空,
  必须先 update),可选 `pip install trimesh`(仅 .ply/.glb/.gltf 需要),然后**镜像 rebuild**——
  restart 不够(系统包与 /app 都是 image-baked);离线部署模板按 offline-prod-deploy-solution
  纪律,该镜像 delta 须进下一次全量 repack。
- `ORCASLICER_BIN` / `PRUSASLICER_BIN` / `CURAENGINE_BIN` 环境变量是挂载现成二进制的逃生口
  (优先于 PATH 查找)。
- `references/slicer-backends.md` 保留上游原文;其中 macOS `brew install --cask orcaslicer` 指引是
  上游文档原文,容器部署一律以上方 Debian 路径为准。
- 输入规则:`.stl/.obj/` 未切片 `.3mf` 直送;`.ply/.glb/.gltf` 执行时经 trimesh 转 STL(trimesh
  缺失时改要 `.stl/.obj/.3mf`);`.step/.stp/.dxf/.svg/.urdf/.sdf` 拒收(v1 设计如此)→ 走第 0 步桥;
  内含 `Metadata/plate_N.gcode` 的已切片 Bambu 3MF 拒绝重切。

## 常见陷阱与纪律(必读)

| 错误 ❌ | 正确 ✅ | 说明 |
|---------|--------|------|
| 把 `.step/.stp` 路径传给 `--input` | 先走第 0 步桥产 STL(also_stl=True) | v1 显式拒收,报 `out of scope` |
| 跳过 dry-run 直接 `--execute` | dry-run 核对 command 后再 execute | 强制纪律:核对可执行文件、输入/输出路径、profile 三者无误 |
| 自己编一个"打印机 profile" | 用真实来源的原生 profile | CuraEngine 无 `-j` definition 直接拒绝切片;编造值 = 给物理机器发假参数 |
| 把 `references/cura-generic-example.json` 当真实 profile 用 | 仅作契约结构示例 | 通用虚构打印机,未对真 CuraEngine 验证 |
| 重切已切片 Bambu `.gcode.3mf` | 尊重 `already_sliced_bambu_3mf` 拒绝 | 内含 `Metadata/plate_N.gcode`,已是打印作业 |
| 把 validate `ok:true` 当"能打" | 仅静态检查通过 | 仍须人工复核 profile 匹配/温度/起止 gcode/坐标系(gcode-validation.md) |
| 期望 validate 改写/删除可疑命令 | 它只告警,不改写 | 未知命令、相对定位边界跳过都是复核提示 |
| 同一 CAD 会话忘写 `.cad_thread_pin` | 先 write_file pin + bash echo 兜底 | bug-324:文件落进错误线程目录 → 下载 404 |
| `--execute` 与 `--dry-run` 同时传 | 二选一 | 脚本显式拒绝同时使用 |

## 工具

- `bash`:**唯一执行入口** —— `python3 /app/skills/public/gcode/scripts/gcode_tool.py
  <discover|inspect|slice|validate>`(gateway Python 3.12,纯标准库,无 pip 依赖)。
- `text-to-cad_create_step`(MCP,独立容器 text-to-cad:8004):仅用于第 0 步网格桥——
  `also_stl=True` 返回 `stl` 路径。本 skill 是 CAD 管线的下游:STEP/STL → 切片 → validate。
- `write_file`:落盘 wrapper profile JSON;.cad_thread_pin(bug-324)。
- `present_files`:展示 `/mnt/user-data/outputs/` 下的 `.gcode`。
- `ask_clarification`:缺关键信息(打印机机型、profile 来源)时问。
- `text-to-cad_inspect_step` / `text-to-cad_search_step_parts`:本 skill 不直接使用(几何自检属
  cad-modeling)。

## 示例(STL 桥 → 切片 → 校验全链)

```
write_file("/mnt/user-data/.cad_thread_pin", "1")            # 钉线程(同会话做 CAD 时)
text-to-cad_create_step(source=<build123d>, output_path="/mnt/user-data/outputs/bracket.step", also_stl=True)
# → {"status":"ok", "stl":"/mnt/user-data/outputs/bracket.stl", ...}

python3 /app/skills/public/gcode/scripts/gcode_tool.py inspect --input /mnt/user-data/outputs/bracket.stl --json
python3 /app/skills/public/gcode/scripts/gcode_tool.py slice --input /mnt/user-data/outputs/bracket.stl \
  --output /mnt/user-data/outputs/bracket.gcode --profile /mnt/user-data/outputs/generic.profile.json \
  --backend auto --dry-run        # 核对 command 与 profile
python3 /app/skills/public/gcode/scripts/gcode_tool.py slice ... --execute
python3 /app/skills/public/gcode/scripts/gcode_tool.py validate --gcode /mnt/user-data/outputs/bracket.gcode \
  --profile /mnt/user-data/outputs/generic.profile.json --json
present_files(...)               # 然后停止工具调用,写最终回复
```

## 当前状态(诚实标注)

**本 skill 已 vendor 但不可启用 —— ready_to_enable=false,必须保持 enabled:false**,直到切片层
被有意加入:

- 切片核心(`slice`):**不可用**。当前**任何容器都没有切片器 CLI**——已实测:deer-flow-gateway
  (agent bash 实际运行处,LocalSandboxProvider,Debian 12)与 eai-flow-text-to-cad 均无
  OrcaSlicer / prusa-slicer / CuraEngine / BambuStudio 二进制;`discover` 返回所有后端
  `available=false`;`slice` 连 `--dry-run` 都失败——后端查找先抛 "not installed",轮不到打印计划。
- 启用前置(见"后端与输入"):① gateway 镜像加 `curaengine`(+ 可选 trimesh)并 rebuild;
  ② 一个**真实**原生 profile(如 Cura fdmprinter 定义 JSON)进入镜像/技能目录;③
  extensions_config.json 登记启用(本次 vendor 刻意不动它)。
- 今天就能用的部分:**inspect + validate 审计模式**——对外部来源 `.gcode` 做纯标准库静态审计
  (validate 需 wrapper profile 提供运动边界);对网格的 `inspect` 也无切片器依赖。`slice` 不可用。
- trimesh:gateway 缺失(**可选**)——只挡 `.ply/.glb/.gltf` 输入;主路径 `.stl/.obj/.3mf` 不需要。
- 真实打印机 profile:仓库未附带任何真实 profile;`references/cura-generic-example.json` 仅为契约
  结构示例(通用虚构打印机),不得当真实 profile 使用。
- `$cad-viewer` 交接:上游 SKILL 要求把产出的 `.gcode` 交给 `$cad-viewer` 预览——本部署**无此
  skill**(我们的 cad-viewer 是浏览器 GLB 预览(`viewer_url`),不能预览 gcode)→ 不做交接,
  最终回复直接给出文件路径并明说"无 gcode 预览"。
- `$bambu-labs` 交接:未 vendor,不存在 → 输出**终止于 validated 纯文本 `.gcode`**,无 Bambu
  `.gcode.3mf` 打包、无打印机 LAN/云交接、不上传任何东西。
- CNC 铣削:不支持(无 mill postprocessor;gcode 在此专指 FDM 3D 打印)。
- 运行时网络:零(脚本全部离线;无任何 API/上传调用)。
