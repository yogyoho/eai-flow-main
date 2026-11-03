# L2 引擎调参外置（阈值可配置） 设计

> 日期: 2026-11-03 ｜ 状态: 已落地（3bc3726c1..43dbf84d1 推送 origin/main-dev-fork）
> 前置: P3.2 spec §8 挂账第二项（阈值可配置）;P3.3 已落地（9bbc33197..21821eea1）
> 范围: 后端 bid_review 扩展内,零上游/harness 改动

## 0. 背景与问题

`attachments.py` 三处调参硬编码：

1. `NEAR_MISS_GATE = 0.75`（:40）——near-miss 门,平件（:76）与复合子行（:171）两处判定;
2. 负证据滤噪 `>= 0.30`（:60）——closest 候选下限;
3. 负证据 top-3 截断 `cands[:3]`（:60）。

调参须改源码+重启,无法按项目/按部署调优。P3.2 挂账点名可配置;且队列下一项「同义词 YAML 外置」需要同一外置机制铺路。

## 1. 机制（裁决1: YAML tuning 文件,非 env/非 extensions_config）

新建 `engine/dicts/tuning.yaml`（默认值=现状,零行为变更）+ `engine/tuning.py` loader：

- **mtime 缓存**: 每次读取 stat 文件 mtime,变化才重读（µs 级开销;bind-mount 热编辑生效,进程内缓存命中零盘 IO）;
- **fail-safe 逐键回落**: 文件缺失/坏 YAML/键值类型错/超范围 → 该键回落默认;yaml 整体解析失败 → 全量默认。bool 显式拒绝（Python `bool` 是 `int` 子类,`true` 不得混入数值键）;
- **范围表**: `near_miss_gate`/`evidence_min_sim` ∈ [0,1],`evidence_top_k` ∈ [1,10]。

选型理由: 与同义词外置同机制同目录（一文件两节,一次铺路）;repo 内随镜像分发（离线部署友好,env 须走 docker/.env 模板链）;extensions_config.json 是 MCP 管理面,不搭引擎调参。

## 2. 键集（裁决2: 仅 3 键）

```yaml
# engine/dicts/tuning.yaml
near_miss_gate: 0.75      # 近似门:池内 sim≥此值 → UNKNOWN(near_miss)
evidence_min_sim: 0.30    # 负证据 closest 滤噪下限
evidence_top_k: 3         # closest 最多条数
```

`verify.py EVIDENCE_SIM_THRESHOLD=0.9` 不入（证据对齐另一关注点,长期稳定,YAGNI）。

## 3. 引擎接线（attachments.py）

- `NEAR_MISS_GATE` 模块常量退役;三处读 `tuning.get(...)`（:60 两参 + :76/:171 门）;
- 相关注释/文档串同步措辞（NEAR_MISS_GATE → near_miss_gate(tuning)）;
- EAI-CUSTOM 注释引用本 spec 日期+§。

## 4. 测试（裁决3: seam 迁移 + loader 单测;默认零翻红）

- `test_bid_review_attachments.py:346` 常量 monkeypatch 改为 `monkeypatch.setattr(tun, "_FILE", tmp yaml)` + `tun._cache = None` 隔离——seam 换成真实 loader 端到端;
- 新增 `test_bid_review_tuning.py`: 缺文件→全默认 / 合法覆盖三键生效（int 键收 int）/ 逐键非法回落（字符串/超上界/超下界）/ 坏 yaml 全默认 / bool 拒绝;
- mtime 缓存行为不专测（同秒重写 mtime 不变,脆）;以 monkeypatch `_cache=None` 做测试隔离;
- 默认值不动 → golden 52 题零翻红、attachments 既有 40 测除 :346 外零改。

## 5. 验收

1. `PYTHONPATH=. uv run pytest tests/test_bid_review_tuning.py tests/test_bid_review_attachments.py tests/test_bid_review_rule_runner.py` 全绿;
2. golden CLI 52/52 exit 0（默认零翻红）;
3. 手改 tuning.yaml（gate 0.90）端到端门移位演示（:346 更新后即证）;
4. ruff 触碰文件全绿;`git diff --stat` 仅 backend/app/extensions/bid_review/ + backend/tests/ + docs。

## 6. 执行方式（裁决4）与挂账

- 429 配额未重置（11-05 14:21）→ 控制器 inline 执行（executing-plans 式）,deviation 如实记录;
- 同文件下一节 `synonyms:` 留给队列下一项（同义词 YAML 外置）,本切片不动;
- mtime 缓存的并发写竞态（stat 与读文件间隙换文件）不处理——最坏一次脏读,下次 mtime 自愈。
