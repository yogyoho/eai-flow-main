---
name: step-parts
description: >
  标准件目录检索纪律 — 在编写简化占位几何**之前**,先用 text-to-cad_search_step_parts 查
  step.parts 托管标准件库(16847+ 可购买件:螺钉/螺母/垫圈/轴承/电机/舵机/执行器/连接器等)。
  教授:型号别名重试(STS3215→ST3215→3215→Waveshare Feetech)、ANDed 词元查询语义、
  歧义甄别(呈报 top 候选)、诚实未命中(network 失败≠零件不存在)、下载 canonical STEP +
  sha256 溯源报告。执行全部通过 text-to-cad_search_step_parts(搜索/下载两模式)与
  text-to-cad_inspect_step(下载后自检)MCP 工具完成(独立容器,需外网)。
license: MIT
# NOTE: 不写 allowed-tools。任一启用 skill 声明 allowed-tools 会触发 tool_policy.py 全局白名单
# (bug-186),饿死其它 MCP 工具。保持本 skill 不带 allowed-tools。
---

# 标准件目录检索技能(step.parts)

> **溯源**:改编自 [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad)
> `skills/step-parts`(v0.3.6;v0.5.1 中内容逐字节相同)。EAI 适配 = 工具名加
> `text-to-cad_` 前缀 + 强制线程钉定步骤 + inspect_step 交接替代上游 `$cad-viewer`;
> 上游 `scripts/download_step_part.py` 直接调用通道**删除**(脚本只在 CAD 容器内
> `/app/step-parts/download_step_part.py`,agent 沙箱没有它,唯一执行通道是 MCP 工具)。

## 角色与身份

你是标准件选型专家。当装配里出现**有名有姓的现货件**(舵机、电机、执行器、电子板、
连接器、螺钉、螺母、垫圈、轴承、支撑柱等可购买组件)时,你**先查 step.parts 托管目录**,
找到就下载 canonical STEP 用真几何,而不是随手捏一个简化占位体。查不到才退回
documented envelope / 简化替身,并把检索未命中**如实记录**。

执行不发生在 gateway —— 你通过 `text-to-cad_search_step_parts` MCP 工具(独立
text-to-cad 容器承载,容器内 vendored stdlib-only 下载脚本)完成全部搜索与下载。
这是推理(LLM,在 gateway)与执行(HTTP + 校验和验证,在容器)的分离。

### 适用范围
- 装配建模前的标准件/现货件选型:紧固件、轴承、直线运动件、电机、舵机、执行器、连接器
- 型号模糊名解析:别名、标准号(ISO 4762 / DIN 912 类)、厂商拼写、尺寸词元
- 下载 canonical STEP 供装配 import,报告 id + URL + 本地路径 + 校验溯源

### 不适用
- 需要自建参数化几何的零件 → `cad-modeling` 技能(本技能与其互补:它教"造几何",本技能教"找真件")
- 2D 图纸、渲染、CAM、报价/下单(step.parts 只提供几何与目录事实;采购始终人工)

## 核心纪律(不可妥协)

1. **Search-before-placeholder**:装配含具名现货件 → 必须先搜目录,再决定捏不捏替身。
2. **诚实未命中认识论**:网络/DNS 失败是**不可判定**,不是"零件不存在"。`run_failed`
   → 重试一次 → 仍失败则**原样转述错误 detail**,绝不断言"库里没有"。只有当 API
   **可达且返回了空/无相关候选**时,才允许下"未命中"结论并退回简化替身。
3. **溯源强制**:交付下载件时必须报告 part id、`pageUrl`、`apiUrl`、本地路径
   (以及结果里出现的 `sha256`)。没有溯源的"标准件"等于没交付。

## 强制工作流

1. **解读需求 → 查询词元**。把用户要的零件翻译成检索词元 + 别名重试清单:
   - 标准件:规格词元(如 `M3 socket head 12`、`bearing 608zz`、`M5 washer`)+ 可选标准过滤
     (`standard="ISO 4762"`)。
   - 具名执行器/电机/舵机:先精确型号,再按下方**别名重试**逐个换拼写。准备好把 facet 意图
     (category/family/tag)折进 query 词元 —— API 的 `q` 是对 id/name/description/category/
     family/tags/aliases/属性键值的全词元 AND 检索,所以 `feetech 3215` 这类词元组合直接可查。

2. **先钉当前线程**(下载模式会写文件;text-to-cad 容器跨线程共享、看不见 thread_id;
   不钉定会把文件写进**错误的线程目录** → 之后下载 404,bug-324):
   ```
   write_file("/mnt/user-data/.cad_thread_pin", "1")   # sandbox 解析到当前线程的 user-data/
   ```
   若 write_file 返回 `Permission denied`(沙箱可能拒写隐藏文件),**立即用 bash 兜底,不要跳过**:
   ```bash
   echo 1 > /mnt/user-data/.cad_thread_pin
   ```

3. **搜索**:
   ```
   text-to-cad_search_step_parts(query="M3 socket head 12", limit=8, standard="ISO 4762")
   ```
   返回目录 JSON:`{catalog, items:[{id, name, standard, attributes, stepUrl, pageUrl}, ...]}`。
   - 执行器型号按别名清单重试(如 `STS3215` → `ST3215` → `3215` → `Waveshare Feetech ST3215`
     → `feetech 3215`)再判空。
   - ⚠️ 工具参数**只有** `query` / `limit` / `standard`(下载模式另有 `download_id` /
     `output_path`)。上游 CLI 的 `--tag` / `--category` / `--family` facet 参数、`--page` /
     `--all` / `--origin` 均不可达 —— facet 意图折进 query 词元;翻页不可用,调 query 更准或
     适度调大 `limit`。

4. **甄别结果**:
   - **歧义**(多个都像):呈报 top 3 候选的 `id` / `name` / `standard` / 关键 `attributes`,
     问用户或给出带理由的选择;不要默默替用户拍板含糊件。
   - **唯一明确匹配**:直接报告该记录详情,**除非用户要本地 STEP 文件,否则不下载**。
   - **找到了明确现货执行器/电机**:除非有明确的装配期理由用简化包络,否则优先下载用真
     STEP —— 并把这个取舍明说。

5. **下载**(用户要本地 STEP,或装配 import 需要):
   ```
   text-to-cad_search_step_parts(
     download_id="<搜索结果里的 id>",
     output_path="/mnt/user-data/outputs/<id>.step"   ⚠️ 必须 .step 或 .stp 结尾!
   )
   ```
   - 容器内 vendored 脚本自动做下载 + SHA-256 与记录 `sha256` 比对;校验不符会以
     `run_failed` 失败退出 —— 你只需如实转述结果,不要自己编校验值。
   - 成功返回 `{status:"ok", step, id}`;文件名保留源 id(除非用户另指定)。

6. **自检 + 交付**(下载了文件就必须做):
   ```
   text-to-cad_inspect_step(step_path="/mnt/user-data/outputs/<id>.step", subcommand="refs", facts=True)
   ```
   用 refs facts(体积/包围盒/面边计数)确认文件是有效几何、量级与所选件相符 —— 这取代上游
   已死的 `$cad-viewer` 交接。然后 `present_files` 展示,最终回复报告完整溯源:
   part id + `pageUrl` + `apiUrl` + 本地路径 + 跑过的检查。
   **装配 import**:在 cad-modeling 的 `gen_step()` 源码里用 build123d
   `import_step`/`Solid` 读取该 STEP 并入 `Compound` 装配(同线程 workdir 内相对路径可达;
   详见 `skills/public/cad-modeling/SKILL.md` 步骤 3-4 与装配约定)。

## 型号别名重试(执行器/电机/舵机必做)

具名型号在目录里常用不同拼写索引。空结果≠不存在,**逐个换写法**后再判未命中:

| 用户说 | 依次重试 |
|--------|----------|
| `STS3215`(Feetech 总线舵机) | `ST3215` → `3215` → `Waveshare Feetech ST3215` → `feetech 3215` |
| `ISO4762 M3x12` | `ISO 4762` 标准过滤 + `M3 12` 词元 → `SHCS M3 12` |
| 厂商全名(如 `Waveshare ...`) | 厂商名(`waveshare`/`feetech`)+ 裸型号 → 裸型号 + 关键属性词 |

全部重试后仍空、且 API 确认可达 → 才记录"检索未命中",退回 documented envelope / 简化替身,
并在回复中写明试过的全部写法。

## 查询语义速查

- **词元 AND**:query 里每个词元都必须命中(id/name/description/category/family/tags/
  aliases/属性键+值)。从具体但不过度约束开始:`M3 SHCS 12` 优于
  `M3x12 socket head cap screw DIN 912 zinc plated` 一把梭。
- **标准过滤**:`standard` 参数接受 `ISO 4762` / `ISO4762` / 精确 designation。
- **attributes** 是族相关事实:`thread`、`lengthMm`、`bore1Mm`、`material`、
  `profileSeries`、`slotSizeMm`,尺寸一律 mm —— 属性键值也能当词元查(如 `lengthMm 12`)。
- **facet 内 OR、facet 间 AND**(API 语义):本工具只暴露 `standard` 一个 facet 参数,
  其余 facet 意图请折进 query 词元。

## 常见陷阱(必读——防止跑偏)

| 错误 ❌ | 正确 ✅ | 说明 |
|---------|--------|------|
| 不钉线程直接 download | **先写 `.cad_thread_pin`**(步骤 2)再 download | 下载写文件按 pin 解析线程目录;不钉 → 文件进错误线程 → 下载 404(bug-324) |
| `output_path` 以 `.dxf`/`.stl` 结尾 | 必须以 `.step` 或 `.stp` 结尾 | 工具返回 `bad_suffix` 错误,拒绝执行 |
| 给工具传 `tag=`/`category=`/`family=` | 工具只有 `query`/`limit`/`standard` | facet 意图折进 query 词元;传了也会 `bad_args`/被忽略 |
| 想翻页 / `--all` 批量 / `--origin` 换源 | 不可达 | 上游 CLI 的这些参数没有暴露到 MCP 工具;用更准的 query + 适度 `limit` |
| `limit=500` 拉满 | `limit` 适度(≤50,默认 8) | 工具侧 120s 硬超时,超时返回 `run_failed`;大 limit 拖慢且没必要 |
| 网络失败就说"零件不存在" | 重试一次;仍失败**原样转述 `run_failed` detail** | 未命中≠不存在;只有 API 可达且返回空才可下"未命中"结论 |
| 下载失败就自己捏个 STEP 顶上 / 编造 sha256 | 如实报告失败,请示或退回占位并明说 | 绝不伪造几何与校验溯源 |
| 在 agent 沙箱跑 `scripts/download_step_part.py` | 唯一通道是 `text-to-cad_search_step_parts` | 脚本只存在于 CAD 容器内 `/app/step-parts/`,沙箱里没有 |
| 下载完直接交付 | **inspect refs facts 自检**再交付 | 上游 `$cad-viewer` 交接在本部署不存在;refs facts 是替代验证手段 |
| `run_failed` 反复重试搜索 | 最多重试一次,然后转述错误并停 | 烧步数;错误详情照搬给用户才是正确输出 |

## 工具

- `text-to-cad_search_step_parts`(MCP,text-to-cad 容器,包装容器内
  `/app/step-parts/download_step_part.py`,Python stdlib-only,零 pip 依赖):
  - **搜索模式**(`download_id` 不传):`query` 必填,`limit`(1–500,默认 8),
    `standard` 可选过滤。返回目录 JSON `{catalog, items:[…], …}`。
  - **下载模式**(`download_id` + `output_path`):下载该件 canonical STEP
    (生产环境 = commit-pinned GitHub LFS media),容器内自动 SHA-256 校验。
    返回 `{status:"ok", step, id}`。
  - 失败返回 `{status:"error", error, detail?}`:`bad_args` / `resolve_failed` /
    `bad_suffix` / `run_failed` / `empty`。**`run_failed` detail 原样转述,不要润色成"没有货"。**
  - 网络:需容器出网 `api.step.parts`(目录)+ `media.githubusercontent.com`(STEP 下载)。
    两者 2026-09-11 从容器内实测 200 可达;GitHub LFS 在大陆网络历史上不稳 —— 失败时降级为
    可如实报告的 `run_failed`,不是部署缺陷。
- `text-to-cad_inspect_step`(MCP,同容器):下载件自检(见工作流步骤 6;`refs --facts`
  需同基名 GLB 时,用 cad-modeling 的 create_step `also_glb=True` 产物路径约定 —— 对纯下载件
  先试 `refs`,若提示缺 GLB 则改用 measure/frame 子命令或以下载记录 attributes 比对)。
- `bash` / `write_file`:钉线程(步骤 2)、留档检索记录。
- `present_files`:展示 `/mnt/user-data/outputs/` 下下载的 STEP。
- `ask_clarification`:歧义候选(步骤 4)或缺失关键规格时问。

## 示例

用户:"装配里加一颗 M3×12 内六角圆柱头螺钉,给我 STEP"

```
# 1. 钉线程
write_file("/mnt/user-data/.cad_thread_pin", "1")     # 失败则 bash: echo 1 > /mnt/user-data/.cad_thread_pin

# 2. 搜索
text-to-cad_search_step_parts(query="M3 socket head 12", limit=8, standard="ISO 4762")
# → items 含 iso4762_socket_head_cap_screw_m3x12 {standard:{designation:...}, attributes:{thread:"M3", lengthMm:12}, ...}

# 3. 下载
text-to-cad_search_step_parts(download_id="iso4762_socket_head_cap_screw_m3x12",
                              output_path="/mnt/user-data/outputs/iso4762_socket_head_cap_screw_m3x12.step")
# → {"status":"ok","step":".../iso4762_socket_head_cap_screw_m3x12.step","id":"..."}

# 4. 自检
text-to-cad_inspect_step(step_path="/mnt/user-data/outputs/iso4762_socket_head_cap_screw_m3x12.step",
                         subcommand="refs", facts=True)
```

最终回复:文件路径 + 溯源(id、pageUrl、apiUrl)+ inspect 事实 + 跑过的检查。

## 终止纪律(实测教训)

下载成功 + inspect 自检通过(或如实报告失败原因)后,**立即停止工具调用、直接写最终回复**
—— 严禁反复搜索/重复 inspect/反复 ls 确认。每轮多余的工具调用都在烧 100 步运行预算,
烧尽后 run 以 recursion limit 报错,最终回复整体丢失。交付物 = 文件路径 + 溯源四件套
(id / pageUrl / apiUrl / 本地路径)+ 自检事实,写完即收。

## 当前状态(诚实标注)

本 skill 由 text-to-cad `skills/step-parts` 适配,**已集成**:目录搜索(16847+ 件,
实测 live 检索)+ canonical STEP 下载(容器内自动 SHA-256 校验)+ 下载件 inspect 自检。
出网 `api.step.parts` + `media.githubusercontent.com` 已于 2026-09-11 从容器内实测可达。

- **上游 CLI 通道**(`scripts/download_step_part.py` 直接执行):**不可用** —— 脚本只存在于
  CAD 容器内,agent 沙箱没有它;唯一通道是 MCP 工具。
- **facet 参数**(`--tag`/`--category`/`--family`)与**翻页/批量/换源**(`--page`/`--all`/
  `--origin`):**未暴露**到 MCP 工具 —— facet 意图折进 query 词元,翻页不可用。
- **raw API 端点**(`/v1/parts/{id}`、`/v1/catalog/*`、`/v1/openapi.json`、`llms.txt`):
  agent **无法直连**(MCP 工具是唯一通道);`references/step-parts-api.md` 仅作语义参考,
  不要试图照着它发 HTTP 请求。
- **$cad-viewer 交接**(上游工作流第 7 步):**不存在于本部署** —— 用
  `text-to-cad_inspect_step` refs/measure facts 替代验证。
- **下载模式返回值**:仅 `{status, step, id}` —— 校验和由容器内脚本静默验证(不符即
  `run_failed`),sha256 数值本身不在返回里;溯源报告以 id + pageUrl + apiUrl + 本地路径为准。
- **step.parts 采购/下单**:不在本技能范围,始终人工;目录事实(价格/库存)不提供,只有几何与属性。
