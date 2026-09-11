---
name: bid-technical
description: 当用户需要编制投标技术卷(技术条款逐条响应、样例库检索仿写/编造+深度目标校准、响应校验落账、章节进度章门、技术卷分册 build 交付)时使用此技能。依赖配对技能 bid-proposal-overall(A)的管线脚本与 workspace 权威态(pair-install, 不可独立分发); 招标文件义务清单提取/整体方案/模拟评分在 A。
---

# 投标技术卷技能(bid-technical, 纯编排——脚本 canonical 在 bid-proposal-overall)

## 前置与分工

- **前置**: A 的阶段0-3 已过确认门1——`clauses.json`/`structure.json`/`entities_whitelist.json` 就绪(snapshot `phase` ∈ {3/4-合并与构建})。缺前置回 A 走阶段0-3, **不代做**。
- **B 负责**: B1 技术卷大纲自拟 → B2 供源级联逐条款响应(4a) → B3 progress 章门 → B4 build `--docs technical`。
- **脚本**: 全部管线脚本在 `/mnt/skills/public/bid-proposal-overall/scripts/`(全量速查表见 A 的 SKILL.md; 本表只列 B 常用子集)。本技能 scripts/ 仅 `bank_compile.py`——**离线维护者工具**(样例入库编译: 脱敏→切片→深度基线→RAGFlow 推送), 不进 Agent 速查表、运行时不调用。

## 铁律(继承 A 全部铁律——state 防改/失败熔断/反弃线/快照纪律同 A, 附加三条)

1. state/ 权威文件只由 A 的管线脚本写盘并签名; B 不新增任何直写途径, 签名校验失败按错误行恢复, 不试错绕行。
2. 响应完备性>溯源性(双轨): 样例库仿写优先→样例库没有**直接编造**合法且必要(标 `fabricated` 全量进人核); **四类硬围栏绝不编造**(报价数字/资质证号/公司实体名(白名单外)/招标原文引用)。
3. `depth_target` 只在样例命中组写(命中段实质长 median 取整), 编造/self 候选不写——不拍脑袋估数; 未写者落库级 absolute_floor 兜底。

## 工作流

### B0 前置核验
跑 A 速查表 snapshot.py 读 `phase`; 确认 clauses/structure/whitelist 在位。

### B1 技术卷大纲自拟(v1 对话协议, 无 UI)
- 输入: A 的 extract 活条款(`category ∈ {technical, service}`)+评分办法条款+`references/tech_outline_packs/` 骨架(16 类登记见其 README; pack 未填充的类别按评分办法关键词自行拟章组)。
- 按评分项关键词把条款聚到骨架类别(确定性关键词匹配起步, 聚类质量进人核)。
- 产出: `candidates/tech_outline.candidates.md`(章组→clause_id 组映射+骨架偏差说明), 对话呈现**确认后**才作为响应推进的组织视图。
- **v1 边界**: 技术卷章结构仍以 structure.json 技术章为准渲染; 大纲自拟当前只组织响应推进次序与章组检索批, 不直写 structure.json(结构化大纲→structure 扩写为后续计划)。

### B2 供源级联响应生成
开始前**先读全篇** `references/tech_response_prompt.md` + `references/build-technical.md`。级联(逐条款按序, 不跳步): 第一层样例库检索(按章组批量, RAGFlow filters; 命中→仿写+写 `depth_target`+`needs_human_verify=true`)→无命中**直接编造**(合法默认, 标 `fabricated`)→self 重组。候选 JSON 即刻落盘 `candidates/`, 逐批跑 A 速查表 `responses.py validate` + `merge`。脱敏语料的 `****` 是掩码: 引用片段避开掩码段, 绝不照抄掩码形态进正文。

### B3 progress 章门
A 速查表 `progress.py init` → 逐章推进 `next`/`mark` → `gate`; FAIL detail 回 B2 补写。深度异常(depth_below_target/depth_below_floor)是质量牵引非废标阻断, 按 build-technical.md 排错处置。

### B4 build --docs technical
A 速查表 `build_output.py … --docs technical`: 只重写技术卷册组+索引卷技术卷节; 整体方案册/副表不触碰(manifest 合并)。交付 present_files 后**确认门2 回 A 走**(补遗 diff+终稿复核两技能一并)。模拟评分在 A(阶段5), B 不产评分报告。

## 命令速查表(B 常用子集——脚本 canonical 在 A, 绝对路径照抄)

```bash
python /mnt/skills/public/bid-proposal-overall/scripts/responses.py validate --candidates /mnt/user-data/workspace/bid/candidates/RESP-tech-001.json --state-dir /mnt/user-data/workspace/bid/state
python /mnt/skills/public/bid-proposal-overall/scripts/responses.py merge --candidates /mnt/user-data/workspace/bid/candidates/RESP-tech-001.json --state-dir /mnt/user-data/workspace/bid/state
python /mnt/skills/public/bid-proposal-overall/scripts/progress.py init --state-dir /mnt/user-data/workspace/bid/state
python /mnt/skills/public/bid-proposal-overall/scripts/progress.py next --state-dir /mnt/user-data/workspace/bid/state
python /mnt/skills/public/bid-proposal-overall/scripts/progress.py gate --state-dir /mnt/user-data/workspace/bid/state
python /mnt/skills/public/bid-proposal-overall/scripts/progress.py mark C-01 DRAFTED --state-dir /mnt/user-data/workspace/bid/state --detail 处置完成
python /mnt/skills/public/bid-proposal-overall/scripts/build_output.py --state-dir /mnt/user-data/workspace/bid/state --out /mnt/user-data/outputs/投标文件 --docs technical
python /mnt/skills/public/bid-proposal-overall/scripts/snapshot.py --workspace /mnt/user-data/workspace/bid --project 项目名称 --code ZB=招标文件
python /mnt/skills/public/bid-proposal-overall/scripts/state_guard.py verify --state-dir /mnt/user-data/workspace/bid/state
```

**防幻觉契约**: A/B 两份速查表之外不存在任何脚本或子命令; 子命令清单以 A 速查表为准。记不准先跑 `<脚本> --help`。所有命令绝对路径, 不 `cd`。

## 排错一级索引

- 响应校验(citations/thin/boilerplate/placement/深度门)/技术卷渲染: build-technical.md 排错表
- 通用(路径/签名/退出码 2、3/熔断): A 的 stage0-2-intake-extract.md 排错表
- 整体方案册"没被本技能 build 改动": 收窄语义不是故障(副表只在 A 的 --docs all 重建)
- 样例入库(bank_compile 残留扫描 rc=1 不出库): 维护者离线操作, 见 scripts/bank_compile.py docstring

## 注意事项

- 不调外部标书 SaaS, 招标文件与标书不出内网; 样例库供源以 RAGFlow bid_samples 域为准(bank_compile 可选推送), 未建库直接编造(完备性优先)。
- 主观评分与商务全量镜像在 A; B 交付物=技术卷册组, 与 A 的整体方案册同目录、manifest 合并、互不清场。
