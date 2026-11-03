# L2 同义词 YAML 外置 设计

> 日期: 2026-11-03 ｜ 状态: 已落地（21b69c401..5bf517f81 推送 origin/main-dev-fork）
> 前置: L2-tuning 已落地（b6d4c548e）——tuning spec §6 承诺的同文件 `synonyms:` 节本切片兑现
> 范围: 后端 bid_review 扩展内,零上游/harness 改动

## 0. 背景与问题

`attachments.py:22-25` `_SYNONYM_GROUPS` 两组硬编码（营业执照/企业法人营业执照、审计报告/年度审计报告）。P3 落地时的 ponytail 注（:19「>20 组外置 engine/dicts/synonyms.yaml」）预告外置;扩组须改源码+重启,与 tuning 同病。

## 1. 机制（裁决1: 同文件 `synonyms:` 节,非独立 synonyms.yaml）

`tuning.yaml` 加 `synonyms:` 节;`tuning.py` 的 `_load` 一次 yaml 解析产出**双验证产物**（数字键 dict + 同义词组元组）,共享同一 mtime 缓存与锁——加一个 accessor 即得,一次 stat 双收益。tuning spec §6 已承诺此节。

```yaml
synonyms:                            # 每组首元素=规范形,余为变体;
  - [营业执照, 企业法人营业执照]        # 组内最长变体优先子串替换,单遍按声明序
  - [审计报告, 年度审计报告]           # (规范形不含他组变体——组间耦合行为未定义);
                                     # 方向不明变体(副本/复印件/回执/正本)不入表
                                     # =防静默升级 MATCHED,它们归 near-miss 门管。
```

选型理由: loader mtime 缓存骨架现成;dicts/ 单文件原则（ponytail）;整节替换语义直观（运维改节即换全表）。

## 2. 失效语义（裁决2: 逐组校验丢弃,节坏回落默认）

- 组校验: 必须是列表、≥2 项、每项非空字符串（首=规范形）;入组前 `strip()`;
- 坏组**丢弃**（不清空全部）;全部坏/节非列表 → 回落默认两组;
- `synonyms: []` 亦回落默认（禁用折叠无真实需求,YAGNI;yaml 注释声明）;
- 数字键与 synonyms 节**互相独立**校验（一边坏不影响另一边）。

## 3. 默认组归宿（裁决3: tuning.py DEFAULTS + yaml 同步数据两处同值）

`_DEFAULT_SYNONYM_GROUPS` 进 tuning.py（模块真源,缺文件=现状行为）;yaml 同节数据同步（运维编辑面）。attachments.py `_SYNONYM_GROUPS` 退役,`_fold_synonyms` 改喂 `tuning.synonym_groups()`;helper 语义（组内最长变体优先/单遍声明序）不变;每组读取走 mtime 缓存（normalize_name O(n²) 调用面,stat µs 级,实测前不优化——ponytail）。

## 4. 测试

- tuning 新增 4: 缺节默认两组 / 覆盖整节替换生效（多组多变体+int 键并存互不干扰）/ 坏组逐个丢弃（单元素组/非字符串项/节内字符串）/ 节非列表回落默认;
- attachments 新增 1 端到端: yaml 自定义组经 `normalize_name` 折叠 + 证整节替换（默认组被换掉非合并）;
- 既有 5 钉零改（默认组不动）;golden 52/52 零翻红。

## 5. 验收

1. `PYTHONPATH=. uv run pytest tests/test_bid_review_tuning.py tests/test_bid_review_attachments.py tests/test_bid_review_rule_runner.py` 全绿（预期 373+5=378/6）;
2. golden CLI 52/52 exit 0;
3. ruff 触碰文件全绿;diff 仅 backend/app/extensions/bid_review/ + backend/tests/ + docs。

## 6. 执行方式（裁决4）与挂账

- 429 配额未重置 → 控制器 inline 执行（同 tuning 切片）,deviation 如实记录;
- 后续队列: 指纹/L0-L5 二期、混合成因 issue 面、子行证据池时点性;
- 运行时生效仍需 gateway 重启（P3.2 起挂账,并发会话风险待用户）;重启后 yaml 热编辑即生效。
