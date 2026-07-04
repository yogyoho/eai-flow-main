---
name: fire-protection-extract
description: |
  ⛔ 用户已上传设计说明书(.docx)并请求编写消防设计专篇 → 用本技能（不用 fire-protection-report-v2）。
  本技能只跑一条流水线命令，报告由脚本自动生成并落盘。你不是报告作者。
  无说明书时改用 fire-protection-report-v2。
---

# 消防设计专篇 — 一键流水线

报告由 `run.sh` 自动生成（解析说明书 → 按契约逐字摘抄 → 溯源校验 → 落盘）。**你的全部工作是两步：跑命令、展示成品。**

## 你的两步操作

### 第 1 步：跑流水线（一条命令完成全部）
```bash
bash /mnt/skills/custom/fire-protection-extract/scripts/run.sh \
  "/mnt/user-data/uploads/<设计说明书.docx>" \
  "<项目名>"
```
- 把 `<设计说明书.docx>` 换成 uploads/ 下实际文件名，`<项目名>` 换成项目名。
- 命令结束时报告已写入 `/mnt/user-data/outputs/<项目名>消防设计专篇.md`。
- 终端最后一行 `REPORT_READY: <path>` 就是成品路径。

### 第 2 步：展示成品
```
present_files(filepaths=["/mnt/user-data/outputs/<项目名>消防设计专篇.md"])
```

完。向用户报告"消防设计专篇已生成"+ grounding 结果即可。

## ⛔ 不要做的事（违反会导致抄错）

- **不要 read_file 设计说明书**（`.docx` 或自动转换的 `.md`）——`run.sh` 内部会读，你不需要理解它的内容。
- **不要 write_file / str_replace 报告内容**——报告已由 `run.sh` 写好；你手动改写会引入抄错（例如把 6589.62㎡ 改成 7026.25㎡、把指标表的数当建设规模）。
- **不要 read_file 脚本或 `fire_spec_mapping.json`**——机器文件，`run.sh` 自动加载。
- **不要手动起草/拼凑报告**——这不是生成式技能。

## 仅在以下情况介入

- **`run.sh` 输出"含失配锚"**：说明书结构与样本契约有差异。按 `references/extractor_rules.md` 校准一份 `workspace` 下的 mapping 副本，设环境变量 `FIRE_EXTRACT_SKILL_DIR` 指向它（或临时改 mapping 路径）后重跑第 1 步。**不要手改报告正文。**
- **§7 投资概算显示 `[需计算]` 是正常的**——说明书无此数据，由概算专业另算。不要补数。
- **大面积失配**：说明书结构与样本差异太大 → `ask_clarification` 告知用户，考虑回退 `fire-protection-report-v2`。

## 参考文件（仅出问题时按需读）
- `references/extractor_rules.md` — 锚点选取/防抄错规则（校准 mapping 时参考）
- `scripts/run.sh` — 流水线入口（执行件，不读直接跑）
