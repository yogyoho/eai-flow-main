---
name: fire-protection-extract
description: |
  ⛔ 当用户已上传设计说明书(.docx)并请求编写消防设计专篇时，应使用本技能，不使用 fire-protection-report-v2。
  本技能从设计说明书**逐字摘抄**重组出消防专篇（映射契约驱动 + 逐字溯源校验），而非从零生成。
  触发词：消防设计专篇/消防设计报告/消防设计篇章 + 有设计说明书。无说明书时改用 fire-protection-report-v2。
---

# 消防设计专篇 — 脚本执行指令

**你是执行器，不是作者。** 报告由流水线自动生成（parse → extract → verify），你的工作只有一个：**按顺序执行下面 3 个 bash 命令**，然后检查结果。

已验证：网关容器已部署 parse_spec / extract / grounding_check 脚本，Python 3.12 环境可用（无 python-docx 时自动回退 stdlib zipfile+xml），映射契约为 JSON 格式（零依赖），以下 bash 命令可直接执行，不需要提前检查环境或阅读脚本源码。

---

## 执行流水线（三步，不可跳步，不可替换为手动操作）

> 把 `<设计说明书.docx>` 替换为 uploads/ 下实际的文件名，`<项目名>` 替换为项目名称。

### 第一步：解析（parse）—— 把 docx 转成结构化数据
```bash
python /mnt/skills/custom/fire-protection-extract/scripts/parse_spec.py \
  "/mnt/user-data/uploads/<设计说明书.docx>" \
  "/mnt/user-data/workspace/<项目名>_struct.json"
```
输出应为 `OK [backend] paras=NNN tables=NNN -> ...`。 记录 paras 和 tables 的数量。

### 第二步：抽取（extract）—— 按映射契约生成报告
```bash
python /mnt/skills/custom/fire-protection-extract/scripts/extract.py \
  "/mnt/user-data/workspace/<项目名>_struct.json" \
  "/mnt/skills/custom/fire-protection-extract/references/fire_spec_mapping.json" \
  "/mnt/user-data/outputs/<项目名>消防设计专篇.md"
```
输出应为 `OK -> ... (NNNNN chars)`。**如果终端输出中出现 `[⚠未找到` 字样，说明锚点失配，需要校准契约。** 此时用 read_file 查看 structure.json 找到正确的锚点文本，复制一份 mapping.json 到 workspace 修改锚点后重新从第二步执行（不要改原始契约文件）。

### 第三步：校验（verify）—— 逐字溯源验证
```bash
python /mnt/skills/custom/fire-protection-extract/scripts/grounding_check.py \
  "/mnt/user-data/outputs/<项目名>消防设计专篇.md" \
  "/mnt/user-data/workspace/<项目名>_struct.json" \
  "/mnt/skills/custom/fire-protection-extract/references/fire_spec_mapping.json"
```
退出码 0 = 通过。非 0 = 阅读 JSON 输出定位失败项，修契约后从第二步重跑，最多 2 轮。

---

## 三步全部通过后

1. 用 read_file 快速浏览报告的开头（前 ~30 行）和结尾（后 ~20 行），确认标题和 8 章结构完整
2. 如报告中有 `[⚠` 标记或 `[需计算]` 以外的缺失——回到第二步校准锚点
3. 用一次 write_file（append=false）把 `/mnt/user-data/outputs/<项目名>消防设计专篇.md` 重新写入（已是最终版本，主要是为了落盘规范化）
4. 调 present_files(filepaths=["/mnt/user-data/outputs/<项目名>消防设计专篇.md"])
5. **（可选但推荐）** 调合规检查：
```bash
python /mnt/skills/custom/fire-regulatory-compliance-check/scripts/compliance_checker.py \
  --report "/mnt/user-data/outputs/<项目名>消防设计专篇.md" \
  --output "/mnt/user-data/outputs/<项目名>消防合规检查报告.md"
```

---

## 参考（仅在出问题时阅读）

- `references/extractor_rules.md` — 锚点选取规则、防抄错机制。仅当需要手动校准锚点时参考。
- `references/fire_spec_mapping.json` — 映射契约（机器文件，extract.py 自动加载），不要直接阅读。
- `scripts/parse_spec.py` / `extract.py` / `grounding_check.py` — 引擎脚本，不要阅读，直接通过 bash 执行。内置 python-docx → stdlib 自动回退。
