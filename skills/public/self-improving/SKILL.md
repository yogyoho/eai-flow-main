---
name: self-improving
description: >
  自进化循环 — 捕获运行中的错误/用户纠正/知识缺口为结构化教训,按 pattern_key 去重折叠,
  重复达到量化门槛后晋升为永久行为规则或提取为新技能,使 agent 在本用户环境下越用越准。
  强制路由:任何涉及"记录教训/记住错误/别再犯/经验沉淀"的请求,必须先读本技能正文
  (/mnt/skills/self-improving/SKILL.md)再动手;教训账本是 custom skill `learnings-ledger`,
  只能用 skill_manage 工具维护,禁止用 user-data 文件或对话内存代替账本。
  触发时机:(1) 命令/工具/API 失败且修复非显而易见,(2) 用户纠正你("不对/应该是/其实…"),
  (3) 用户要的能力不存在,(4) 发现可复用的更好做法,(5) 意识到所依赖知识过时,
  (6) 非平凡任务开工前(先回顾既有教训)。
---

# Self-Improving Loop(自进化循环)

把单次失败变成可计数的教训;教训重复到门槛就改变行为或变成新技能。**学习是延迟的**:你只负责捕获和折叠,晋升/提取必须满足本文的量化门槛,不满足就不动。

## 0. Ledger 初始化(首次捕获时)

ledger 是一个 per-user custom skill `learnings-ledger`,通过 `skill_manage` 维护。首次捕获时若读取 `/mnt/skills/learnings-ledger/SKILL.md` 失败,则创建:

```
skill_manage(action="create", name="learnings-ledger", content=<下方模板>)
```

create 撞名即说明已存在(幂等),改走读取。模板:

```markdown
---
name: learnings-ledger
description: "User lessons ledger [learn:0]. Read /mnt/skills/learnings-ledger/SKILL.md before non-trivial tasks."
---

# Learnings Ledger

条目区只放 pending;resolved 移入归档区(压一行)。

<!-- LEDGER-START -->

<!-- LEDGER-END -->

## Resolved archive
(格式: `- [L-xxx] key ×N 一句话结论 @YYYY-MM-DD`)
```

## 1. 触发表(何时捕获)

| 触发 | kind |
|---|---|
| 用户纠正你("不对/应该是/其实/No, that's wrong…") | correction |
| 命令/工具失败,且修复非显而易见 | error |
| 用户要的能力不存在("能不能顺便…") | feature_request |
| 外部 API/依赖/服务调用失败 | error |
| 你依赖的知识过时(文档/版本/行为与实际不符) | knowledge_gap |
| 发现可复用的更好做法(而非一次性技巧) | best_practice |

**开工前硬规则**:非平凡任务(新功能/调试/多步操作)开始前,先读 `/mnt/skills/learnings-ledger/SKILL.md` 的条目区——已有教训优先复用,别再踩一遍。

## 2. 抑制规则(何时不捕获)

1. 已在本次 run 内解决且原因显而易见的瞬态失败(typo、漏参数、路径手滑)——不捕
2. ledger 里已有同 pattern_key 条目——**折叠,不新增**(见 §4)
3. 用户闲聊性抱怨、无具体错误的模糊不满——不捕
4. 含密钥/凭据的内容——先按 §3 脱敏,脱不干净就不捕

## 3. 捕获纪律(固定顺序,不可换)

1. **脱敏**:token/secret/password/api_key 赋值、Bearer 头、sk-/ghp_/xox[baprs]-/AKIA 开头串、eyJ 开头 JWT 一律替换为 `<REDACTED>`
2. **fence 转义**:evidence 里的 ``` 全部写成 '''(防止截断后 markdown 越狱)
3. **截断**:evidence ≤200 字符,超出加 `…`
4. **先记录后深究**:确认失败类别后立即入账;拿不准精确 pattern_key 就先用 `runtime.failure` 记 pending,后续遇到同主题再折叠时细化 key。**不要为写一条账本做环境考古**——被沙箱策略拦截的探针每次都消耗 run 步数,写账本永远优先于完善诊断

## 4. 折叠协议(reuse-before-mint)

捕获前**必须先读 ledger**:
1. grep 条目区找同 `pattern_key` → 命中则折叠,更新 `count+1`、`last`、`threads` 追加当前 thread 短 id;**不新建**。若命中条目是 `status:resolved`,同时把状态翻回 `status:pending`(教训再次发生=重新打开)
2. 未命中才新建条目,ID 取条目区最大 L 序号 +1

**折叠的逐字调用模板**(参数名是 `replace`,不是 new_str/new_string;patch 只认 find/replace/expected_count):

```
skill_manage(action="patch", name="learnings-ledger",
  find="### L-014 | error | deps.module-not-found | status:pending | count:2",
  replace="### L-014 | error | deps.module-not-found | status:pending | count:3",
  expected_count=1)
```

**新建条目的逐字调用模板**(在结束哨兵行前插入;只允许同 pattern_key 折叠,**禁止把新错误折进不相关条目**):

```
skill_manage(action="patch", name="learnings-ledger",
  find="<!-- LEDGER-END -->",
  replace="### L-015 | error | infra.systemd-absent | status:pending | count:1\nsummary: 容器内无 systemd,systemctl 不可用\nevidence: '''/bin/bash: line 1: systemctl: command not found'''\nfirst: 2026-09-13 | last: 2026-09-13 | threads: t9a2c\naction: 用 service 或直连容器命令替代\n\n<!-- LEDGER-END -->",
  expected_count=1)
```

## 4a. 工具使用契约(违反会连环报错耗尽步数)

- ledger 的 **SKILL.md 本体**只能用两种动作修改:`edit`(全量重写,需传完整 content)或 `patch`(定点 find/replace)
- `write_file` / `remove_file` **仅用于 references/assets 等附属文件**——对 SKILL.md 用必然报错("Supporting file path must be relative" 等)
- **禁止直接路径读写** `/mnt/skills/...`(只读投影,不可写);一切修改走 skill_manage
- **循环守卫:同一操作连续失败 2 次(含参数名写错、报"xx required"类错误)→ 立即改用 `action="edit"` 传完整 SKILL.md 全文重写一次**;再失败就放弃本操作(捕获已成功即止,绝不为次要字段耗尽 run 步数)。禁止退化为直接路径写 /mnt/skills

## 5. 条目格式(正典 schema,与平台 P1 SQL 同构——勿改字段)

```markdown
### L-014 | error | deps.module-not-found | status:pending | count:2
summary: pnpm install 在 node:22 镜像缺 node-gyp
evidence: '''ERR! 404 …'''
first: 2026-09-12 | last: 2026-09-14 | threads: t1,t2
action: 基础镜像预装 build-essential
```

- `pattern_key = area.symptom`,area/symptom 从 `references/pattern-keys.md` 的枚举里选,**不自造**
- `threads` 记 thread id 前 4-6 位即可(跨 thread 数用于晋升门槛)

## 6. [learn:N] 计数器(捕获/解决后必做,但防循环)

ledger 的 description 里的 `[learn:N]` = 条目区 pending 条数。**每次捕获/折叠/resolve 后**,用 `skill_manage(action="patch", name="learnings-ledger", find="[learn:旧N]", replace="[learn:新N]", expected_count=1)` 同步。
**守卫:计数 patch 最多尝试 1 次**——失败(找不到目标串/校验拒)就放弃,绝不重试(计数过期无害;在此处循环重试会耗尽递归上限把整个 run 拖死)。

## 7. 解决(resolve)

问题确认已修(代码改了/配置补了/技能更新了):patch 该条目 `status:pending`→`status:resolved`,整行移入 `## Resolved archive` 压成一行(移动 = 在条目区 patch 删除该行 + 在 archive 区 patch 追加一行,均为定点 replace):

```
- [L-014] deps.module-not-found ×2 预装 build-stdlib 已根治 @2026-09-15
```

resolved 条目不再计入 [learn:N]。

## 8. 晋升(行为进化——门槛达标才做)

**门槛:count≥3 且 threads≥2 个 且 last-first≤30 天。** 三者缺一不晋升。

达标后把教训压缩成**祈使句规则**,晋升到注入面:
- workspace 会话:`skill_manage` 写 `learned-behaviors` skill(不存在则 create),规则放 **description**(每次对话永久注入);正文放完整背景
- 自定义 agent 会话:改用 `update_agent` 把规则写进该 agent 的 SOUL.md

晋升后原条目 `status:pending`→`status:promoted`。规则示例:`"pnpm 项目禁止 npm install;先查 lockfile 再选包管理器"`。

## 9. 提取(能力进化——5 条件之一)

满足任一即可把教训提取为**独立新技能**:
1. 有 ≥2 条 See-Also 级的同类条目(重复问题)
2. status 已 resolved 且修复验证有效
3. 当初需要真实调试/调查才发现(非显而易见)
4. 跨项目可复用(非本项目特有)
5. 用户明说"记住这个做法/存成技能"

流程:`skill_manage(action="create", name=<新技能名>, content=<SKILL.md>)`(name 小写连字符,撞名 fail-closed);成功后原条目标 `status:promoted_to_skill`,并加一行 `skill: <新技能名>` 回链。**无用户确认不自动提取。**

## 10. 自愈(ledger 损坏时)

patch 报 "Patch target not found"(哨兵被外部编辑破坏):
1. 重读 ledger 全文
2. 丢失 `<!-- LEDGER-START/END -->` 则 patch 补回(或用 edit 重写骨架,保留全部条目)
3. 重试原操作

条目区 ~50 条时:把已 resolved 条目全部压行进 archive,为条目区瘦身。

## 11. 边界

- 只捕获**事实性教训**,不捕获用户隐私、无关情绪、一次性任务细节
- 晋升/提取永不需要用户批准之外的自动动作;拿不准就不晋升(学习是延迟的)
- 本 skill 被禁用(技能设置页)即整环停转,ledger 数据仍在原处不丢
