---
name: bambu-labs
description: >
  Bambu Lab 局域网打印交接 — 从已校验的纯 .gcode 出发,经 预检 status → dry-run 交接 →
  FTPS 上传 →(显式授权后)MQTT 启动/暂停/取消 的强制工作流。dry-run 优先,
  真实打印机流量必须 --execute。本 skill 不切片(无 slicer)。
license: MIT
# NOTE: 不写 allowed-tools。任一启用 skill 声明 allowed-tools 会触发 tool_policy.py 全局白名单
# (bug-186),饿死其它 MCP 工具。保持本 skill 不带 allowed-tools。
---

# Bambu Lab LAN 打印交接技能

## 角色与身份

你是局域网 3D 打印交接专家,负责把**已经存在且已校验**的纯 `.gcode` 文件安全地
交给用户的 Bambu Lab 打印机(FTP 上传 + MQTT 启动/暂停/取消)。

执行完全发生在 agent 沙箱内:一个 **100% Python 标准库**脚本
(`bambu_lan_print.py`,手写 socket+ssl MQTT、ImplicitFTP_TLS),零 pip 依赖,
不调用任何 text-to-cad_* MCP 工具、不依赖 CAD 容器。
**本 skill 不切片模型** —— 没有 slicer,STL→gcode 不在本 skill 范围内。

### 适用范围
- 拿到已校验纯 `.gcode` 后的:打印机配置、状态读取、dry-run 交接计划、
  FTPS 上传(upload / upload-start)、打印控制(pause / cancel / clear-error)
- 新打印机上手引导(触屏找 IP + LAN 访问码,开 LAN Only + 开发者模式)

### 不适用
- 切片(无 slicer CLI);建模(`cad-modeling` 负责 STEP/STL);
- 云端/物联网远程打印(仅局域网直连);非 Bambu 品牌打印机

## 强制工作流

1. **输入契约(硬性)**。本 skill 只接受**已校验的纯 `.gcode`**。
   Agent 在当前沙箱**无法切片**(镜像里没有 OrcaSlicer / prusa-slicer / CuraEngine)——
   `.gcode` 必须由用户在自己的电脑上用 OrcaSlicer / Bambu Studio 切好并提供,
   或由外部流程产出。`cad-modeling` 只产出 STEP/STL,切片不在其范围。
   没有 `.gcode` 就没有可做的工作:如实告知用户需要自行切片,不要编造 gcode。

2. **配置打印机**。用户提供打印机局域网 IP + LAN 访问码(凭证属于用户,不要索要
   序列号——用 `serial` 子命令从打印机 TLS 证书抓取,或让 `send` 自动缓存)。
   **必须显式传 `--config`**,把配置落到线程的 user-data(明文访问码随线程留存,
   不落到共享工作区根目录;沙箱中 INIT_CWD 未设置,脚本默认路径是当前目录):
   ```bash
   python3 /mnt/skills/public/bambu-labs/scripts/bambu_lan_print.py config set \
     --config /mnt/user-data/bambu-printers.json \
     --printer a1-mini \
     --host 192.168.1.34 \
     --access-code 12345678 \
     --model a1-mini \
     --fetch-serial
   ```
   新打印机 / 上手引导请求:先读 `references/new-printer-onboarding.md`,带用户在
   触屏上找到 IP 和 LAN 访问码,开 **Enable LAN Only** + **Enable Developer Mode**。

3. **预检 status(第一次真实联网命令,强制)**:
   ```bash
   python3 /mnt/skills/public/bambu-labs/scripts/bambu_lan_print.py status \
     --config /mnt/user-data/bambu-printers.json \
     --printer a1-mini \
     --push-all \
     --wait-seconds 10
   ```
   **预检规则**:连接失败(TCP 到 `192.168.x.x:8883` / `:990` 不通)→ 报告
   "打印机不可达",**立即停止**——沙箱到用户局域网的可达性未经验证,重试无意义。
   脚本默认拒绝非私网地址(需 `--allow-nonprivate-host` 才放行),保持默认。

4. **dry-run 交接 → 仅上传 → 上传并启动**。先 dry-run 看完整 JSON 计划,再
   upload-only,上传成功后才允许 upload-start:
   ```bash
   # dry-run(无 --execute,只打印计划,不碰打印机)
   python3 /mnt/skills/public/bambu-labs/scripts/bambu_lan_print.py send \
     --config /mnt/user-data/bambu-printers.json \
     --printer a1-mini \
     --gcode /mnt/user-data/inputs/job.gcode \
     --handoff template-project \
     --template-project /mnt/user-data/same-printer-template.gcode.3mf \
     --action upload-start
   # 用户明确要求打印时,校验/状态/上传全过后加 --execute --confirm-start-print
   ```
   - `--handoff template-project` 是唯一经实测的 A1 Mini 启动路径:以同型号打印机
     的已知良好 `.gcode.3mf` 为模板,替换 `Metadata/plate_N.gcode` 后整体上传。
     模板 `.gcode.3mf` 必须由人用 OrcaSlicer/Bambu Studio 从真实打印导出一次,
     **不是** CAD 网格 3MF(脚本要求内含 `Metadata/plate_N.gcode`)。
   - `--handoff plain` 仅留作诊断(A1 Mini 上传成功但 `gcode_file` 启动失败/被忽略)。
   - `--handoff bambox-project` **在本部署不可用**(沙箱无 `bambox` CLI,且仅 P1S)。
   - **授权边界**:用户明确说"打印/启动这个任务"即视为 live-start 授权,直接走
     `--execute --confirm-start-print`(不再为物理检查二次确认,但仍要做校验、
     看状态、优先 upload-only、陈述物理检查项、异常即停);用户只要求"准备/上传/
     看看"则在启动请求前停止。真实启动前向用户陈述物理检查:清空 build plate、
     正确的板/耗材/喷嘴、周围安全、有人在场。MQTT publish 只是启动请求,
     以打印机状态/UI 与现场观察为准。

5. **交付与终止纪律(实测教训)**。每次操作后读一次 status 确认打印机状态变化,
   然后把结果(dry-run 计划 / 上传结果 / 打印机状态 JSON / 物理检查清单)写进
   最终回复,**立即停止工具调用**——严禁反复 status/ls/确认循环(会烧尽 100 步
   运行预算,run 以 recursion limit 报错,最终回复整体丢失)。

## 常见陷阱与失败模式(必读)

| 症状 ❌ | 处置 ✅ | 说明 |
|---------|--------|------|
| A1 Mini 上 `gcode_file` 返回 `result: fail` 或停在 `IDLE` | 换 `--handoff template-project` | 纯 gcode 上传成功但固件拒绝/忽略本地直启;plain 只留诊断用 |
| `cache/` 下项目启动后 `print_error: 83935248` / `0500-C010` | `clear-error --execute` 清错;项目交接改传 FTPS 根目录,`url` 用 `ftp:///<name>.gcode.3mf` | 不要用 `cache/` 路径做项目启动 |
| `file:///sdcard/cache/...` 或本地 HTTP URL "看起来接受"但什么都不启动 | 停用该 URL 形式 | 已知死路 |
| FTPS 登录成功但上传 `553` / 缺 `cache/` | 先查打印机存储/SD 卡状态 | 存储问题,不是协议问题 |
| MQTT status 正常但启动无效 | 核对 serial、访问码、开发者模式/LAN Only、确切交接 payload | 逐项排查后再重试 |
| 开发者模式后残留 `gcode_state: FAILED` / HMS | `clear-error --execute` + 打印机断电重启 | 再重试本地启动 |
| 连接 `192.168.x.x` 直接超时 | 报告"打印机不可达"并停止 | 沙箱→用户局域网可达性未验证;不要盲目重试 |
| 忘记 `--config` | 配置落在共享工作区根目录(cwd) | 明文访问码泄露面扩大;始终显式 `--config /mnt/user-data/bambu-printers.json` |
| 非私网 IP 被拒 `Refusing unless --allow-nonprivate-host is set` | 这是安全特性 | 保持拒绝;确属私网打印机时才检查地址写错没有 |
| macOS 上 Bambu Studio/OrcaSlicer 项目导出崩溃 | 不要反复重试 GUI 导出 | OrcaSlicer 出纯 `.gcode`,交接交给本 skill |

调试辅助:`send` 加 `--mqtt-qos 1 --wait-after-publish 10` 观察打印机是否
确认了 MQTT publish 及其后的状态;`serial --json` 抓取/缓存序列号。

## 打印控制(运行中的打印)

对运行中的打印用专用命令,只发控制请求,不上传文件、不开新任务;执行后读
status 确认状态变化。pause/cancel 默认 dry-run;**取消打印需要
`--execute --confirm-cancel-print`**:

```bash
# dry-run payload
python3 /mnt/skills/public/bambu-labs/scripts/bambu_lan_print.py pause \
  --config /mnt/user-data/bambu-printers.json --printer a1-mini
# 执行 + 收打印机回报
python3 /mnt/skills/public/bambu-labs/scripts/bambu_lan_print.py pause \
  --config /mnt/user-data/bambu-printers.json --printer a1-mini \
  --execute --mqtt-qos 1 --wait-after-publish 10
# cancel(dry-run);执行需用户明确要求取消/停止,加 --execute --confirm-cancel-print
python3 /mnt/skills/public/bambu-labs/scripts/bambu_lan_print.py cancel \
  --config /mnt/user-data/bambu-printers.json --printer a1-mini
```

## 工具

- `bash`:唯一执行通道 —— 上述所有 `python3 /mnt/skills/public/bambu-labs/scripts/bambu_lan_print.py ...` 命令。
  脚本纯标准库(ftplib/ssl/socket/zipfile/hashlib/ipaddress/argparse),沙箱 python3 ≥3.10 直接可跑,
  无 pip 依赖、无外部二进制(`bambox` 除外,本部署没有)。
- `read_file` / `write_file`:读用户给的 `.gcode`/模板路径元信息、写 `bambu-printers.json`(或直接用 `config set`)。
- `ask_clarification`:缺 IP/访问码/打印意图时问。
- **不使用** `text-to-cad_*` 任何工具,也没有 `.cad_thread_pin` 钉定步骤 —— 本 skill
  不碰 CAD 容器,不需要线程钉定(那是 cad-modeling 的 text-to-cad_create_step 前置步骤)。

## 当前状态(诚实标注)

本 skill 由 text-to-cad 上游(earthtojake/text-to-cad)适配,**脚本能跑,周边能力缺失**:

- **切片:不可用** —— 沙箱镜像无任何 slicer CLI(OrcaSlicer / prusa-slicer / CuraEngine 全部缺席),
  STL→gcode 被阻断;`.gcode` 必须由用户在自己机器上切好提供。端到端"模型→打印"管线在当前部署不存在。
- **打印机:不存在/未验证** —— 本部署没有任何已知的 Bambu 打印机;沙箱 pod → 用户局域网
  (192.168.x.x 的 990/8883 端口)可达性未验证。第一次 `status` 就是可达性判据,不通即停。
- **凭证:属于用户** —— LAN 访问码由用户提供,明文存 `/mnt/user-data/bambu-printers.json`
  (线程 user-data,随线程隔离),不要写进代码/回复/git。
- `bambox`:**缺席** —— `--handoff bambox-project` 不可用(上游也仅对 P1S 启用);
  A1 Mini 路径走 `template-project`,不需要它。
- 模板 `.gcode.3mf`:**需人工导出** —— 每个打印机型号一次,OrcaSlicer/Bambu Studio 从真实打印导出;
  cad-modeling 的 `--3mf` 边车产物是 CAD 网格 3MF,**不能**替代(脚本要求 `Metadata/plate_N.gcode`)。
- cad-viewer 交接:**N/A** —— 本部署的 CAD Viewer(`viewer_url` 3D 链接)是 GLB-only viewer,
  打不开 `.gcode` 或切片 `.3mf`;上游的 "$cad-viewer handoff" 段已删,不要尝试交接,如实说明即可。
- 上游其余引用文档原样保留:`references/new-printer-onboarding.md`(新打印机上手)、
  `references/local-lan-protocol.md`(协议细节)、`references/real-printer-checklist.md`(首次实机检查清单)。
- **启用状态:未启用(ready_to_enable=false)** —— 上述缺口补齐前启用只会让 agent 的每条
  live 路径死胡同。启用 = 硬件到位、用户供 gcode 后,在 extensions_config.json 的 skills 段
  加 `"bambu-labs": {"enabled": true}` 翻一个开关即可(本仓库未改动该文件)。
