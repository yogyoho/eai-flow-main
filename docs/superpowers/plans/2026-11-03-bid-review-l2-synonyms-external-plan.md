# L2 同义词 YAML 外置 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans（控制器 inline 执行,429 配额裁决见 spec §6）。步骤用 `- [ ]` 勾选。
> spec: `docs/superpowers/specs/2026-11-03-bid-review-l2-synonyms-external-design.md`

**Goal:** `_SYNONYM_GROUPS` 外置 tuning.yaml `synonyms:` 节,loader 双产物共享 mtime 缓存,逐组校验丢弃坏组,节坏回落默认两组,行为零变。

**Architecture:** tuning.py 扩 `_DEFAULT_SYNONYM_GROUPS` + `_norm_groups` 校验 + `synonym_groups()` accessor → attachments.py `_fold_synonyms` 改喂 loader,常量退役。

**Tech Stack:** Python 3.12/PyYAML/pytest。

---

### Task 1: 文档

- [x] spec + plan 落盘提交。

### Task 2: loader 扩展 + yaml 节 + 接线 + 测试(TDD)

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/tuning.py`(DEFAULT 组+校验+accessor+缓存三元组)
- Modify: `backend/app/extensions/bid_review/engine/dicts/tuning.yaml`(synonyms 节+头注更新)
- Modify: `backend/app/extensions/bid_review/engine/attachments.py`(常量退役+_fold_synonyms 喂 loader)
- Modify: `backend/tests/test_bid_review_tuning.py`(+4)
- Modify: `backend/tests/test_bid_review_attachments.py`(+1 端到端)

- [x] **Step 2.1: 先写测试** tuning 追加:

```python
def test_synonym_defaults_when_file_missing(isolated_tuning: Path) -> None:
    assert tun.synonym_groups() == (
        ("营业执照", "企业法人营业执照"),
        ("审计报告", "年度审计报告"),
    )


def test_synonym_override_replaces_section(isolated_tuning: Path) -> None:
    isolated_tuning.write_text(
        "evidence_top_k: 5\n"
        "synonyms:\n"
        "  - [中标通知书, 招标中标通知书]\n"
        "  - [资质证书, 资质证明文件, 资质文件]\n",
        encoding="utf-8",
    )
    assert tun.synonym_groups() == (
        ("中标通知书", "招标中标通知书"),
        ("资质证书", "资质证明文件", "资质文件"),
    )
    assert tun.get("evidence_top_k") == 5  # 数字键与 synonyms 节互不干扰


def test_synonym_bad_groups_dropped(isolated_tuning: Path) -> None:
    isolated_tuning.write_text(
        "synonyms:\n"
        "  - [营业执照, 企业法人营业执照]\n"
        "  - [只有一项]\n"
        "  - [混合, 123, true]\n"
        "  - 不是列表\n",
        encoding="utf-8",
    )
    assert tun.synonym_groups() == (("营业执照", "企业法人营业执照"),)


def test_synonym_section_not_a_list_falls_back(isolated_tuning: Path) -> None:
    isolated_tuning.write_text('synonyms: "oops"\n', encoding="utf-8")
    assert tun.synonym_groups() == (
        ("营业执照", "企业法人营业执照"),
        ("审计报告", "年度审计报告"),
    )
```

attachments 追加（归 :44 同义词测试区）:

```python
def test_synonym_groups_yaml_override_end_to_end(monkeypatch, tmp_path):
    """同义词外置端到端(L2 同义词外置 spec 2026-11-03 §3):yaml 自定义组经
    normalize_name 折叠;且证整节替换(默认组被换掉,非合并)。"""
    from app.extensions.bid_review.engine import tuning as tun

    tuning_yaml = tmp_path / "tuning.yaml"
    tuning_yaml.write_text("synonyms:\n  - [履约保函, 履约保证函]\n", encoding="utf-8")
    monkeypatch.setattr(tun, "_FILE", tuning_yaml)
    monkeypatch.setattr(tun, "_cache", None)
    assert normalize_name("履约保证函") == "履约保函"
    assert normalize_name("企业法人营业执照") == "企业法人营业执照"  # 整节替换
```

- [x] **Step 2.2: 验红** `PYTHONPATH=. uv run pytest tests/test_bid_review_tuning.py -x -q` → AttributeError: synonym_groups。

- [x] **Step 2.3: loader 实现**——tuning.py 三处改:

模块真源 + 缓存形状扩三元组:

```python
_DEFAULT_SYNONYM_GROUPS: tuple[tuple[str, ...], ...] = (
    ("营业执照", "企业法人营业执照"),
    ("审计报告", "年度审计报告"),
)

_cache: tuple[float, dict[str, float | int], tuple[tuple[str, ...], ...]] | None = None
```

`_load` 重构（解析一次双产物;数字键逻辑原样;synonyms 节独立校验）:

```python
def _norm_groups(data: object) -> tuple[tuple[str, ...], ...] | None:
    """synonyms: 节校验(L2 同义词外置 spec 2026-11-03 §2):组=≥2 个非空字符串
    的列表(首=规范形,入组前 strip);坏组逐个丢弃;全坏/节非列表 → None(回落默认)。"""
    if not isinstance(data, list):
        return None
    groups: list[tuple[str, ...]] = []
    for g in data:
        if not isinstance(g, list) or len(g) < 2:
            continue
        if all(isinstance(s, str) and s.strip() for s in g):
            groups.append(tuple(s.strip() for s in g))
    return tuple(groups) if groups else None
```

`_load` 内 `merged` 后并行产 groups;缺失文件分支与缓存命中分支返回 `(merged, groups)`;`get(key)` 改 `return _load()[0][key]`;新增:

```python
def synonym_groups() -> tuple[tuple[str, ...], ...]:
    return _load()[1]
```

docstring 头注同步（「同文件 synonyms: 节留给同义词外置切片」→「synonyms: 节已外置」+校验语义一句）。

- [x] **Step 2.4: yaml 节** tuning.yaml 尾部追加+头注更新:

```yaml
synonyms:                            # 每组首元素=规范形,余为变体;组内最长变体优先
  - [营业执照, 企业法人营业执照]        # 子串替换,单遍按声明序(规范形不含他组变体——
  - [审计报告, 年度审计报告]           # 组间耦合行为未定义)。方向不明变体(副本/复印件/
                                     # 回执/正本)不入表=防静默升级 MATCHED(归近似门管)。
                                     # 空节/坏组回落模块默认;整节替换语义(改节=换全表)。
```

- [x] **Step 2.5: attachments.py 接线**——:22-25 `_SYNONYM_GROUPS` 常量删除,:16-19 注释改（外置声明+ponytail 注更新为「已外置 tuning.yaml synonyms: 节」）:

```python
def _fold_synonyms(t: str) -> str:
    """组内变体子串替换到规范形;单遍按声明序,组间耦合行为未定义(规范形不含他组变体)。
    组表外置 tuning.yaml synonyms: 节(L2 同义词外置 spec 2026-11-03 §3,EAI-CUSTOM);
    mtime 缓存命中零盘 IO,stat µs 级——O(n²) 调用面实测前不优化。"""
    for group in tuning.synonym_groups():
        for variant in sorted(group[1:], key=len, reverse=True):
            if variant in t:
                t = t.replace(variant, group[0])
    return t
```

- [x] **Step 2.6: 验绿** tuning 9 测(5 存量+4 新)+attachments 41(40+1 端到端)全过。

- [x] **Step 2.7: 全家+golden+ruff** family 378/6;golden 52/52;`ruff check`+`ruff format` 四文件。

- [x] **Step 2.8: commit**(显式路径)

```bash
git add backend/app/extensions/bid_review/engine/tuning.py backend/app/extensions/bid_review/engine/dicts/tuning.yaml backend/app/extensions/bid_review/engine/attachments.py backend/tests/test_bid_review_tuning.py backend/tests/test_bid_review_attachments.py
git commit -m "feat(bid-review): L2-synonyms① 同义词外置——tuning.yaml synonyms: 节(loader 双产物共享 mtime 缓存);逐组校验丢弃坏组/节坏回落默认两组/整节替换语义;_SYNONYM_GROUPS 常量退役 _fold_synonyms 喂 loader;端到端 yaml 自定义组折叠+整节替换证;5 新测;默认零变(golden 52/52)"
```

### Task 3: 全量验证收尾

- [x] **Step 3.1**: bid_review 全家 pytest(预期 378/6)。
- [x] **Step 3.2**: spec 状态落定+plan 勾选 commit;push 重试至 `0\t0`。
- [x] **Step 3.3**: .wolf/memory+cerebrum、auto-memory、终报。

---

## 执行约束

同 tuning 切片:main-dev-fork 不中途 push;外来 WIP 禁碰;不碰 .wolf/(控制器统一记);中文 Write/Edit;行号快照先读现场;默认零翻红铁律。
