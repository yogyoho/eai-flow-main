"""bug-3428 回归: F1a 标题排除表头行 / F1b 复合表头拆分 + 129 表命中映射固化。

F1a: match_seed 的标题文本只取非表头行——'物资名称'类列头格不得被 seed 标题
关键词('物资')假命中而劫持 seed 选择(上浦 msm-sc→sp-gj 翻转);吞掉的标题行
(表名所在)不在表头行集合内,仍参与命中。
F1b: name/spec 锚命中同一表头格且左邻格表头为空串时重绑 name→左邻, spec→本格
(木饰面 复合表头形态),门控缺一不可。
129 表回放: 全语料(7 文档)逐表 match_seed 命中映射与固化基线逐一比对——
OCR 缓存仅在容器内可达,宿主机跑套件时 skip(合成 fixture 测试不受影响)。"""

import json
import os

import pytest

from scripts.seed_library import DEFAULT_TABLE_SEEDS, normalize_seeds
from scripts.table_classifier import (
    _collapse_header,
    _title_text,
    extract_items_seed,
    match_seed,
)

SEEDS = DEFAULT_TABLE_SEEDS

# 上浦 p5/t0 实测两级表头结构(裁剪至判别所需列,列位保持): r0 列表头,
# r1 二级单格行('规格'被 collapse 吞为标题行、不入合并表头),无表名标题行。
# 修复前: msm-sc 靠表头格'物资名称'假命中标题词'物资',以 (1,6,-13) 压过 sp-gj (0,7,-9);
# 修复后: msm-sc 标题命中归零,sp-gj 以 7 角色胜出且 spec→c1。
_SHANGPU_ROWS = [
    ["物资名称", "材质", "计量 单位", "暂定数量", "网价 基准价 (元 /t)", "综合费 用（元 /t)",
     "不含税单 价（元/t）", "税金 （元）", "含税单 价（元 /t)", "含税总价 （元）", "备 注"],
    ["", "规格", "", "", "", "", "", "", "", "", ""],
    ["线材", "HPB300Φ8", "吨", "2.288", "6030", "260", "5566.37", "723.63", "6290", "14391.52", ""],
    ["螺纹钢", "HRB400E20", "吨", "25.57", "5660", "260", "5238.94", "681.06", "5920", "151374.40", ""],
]

# 木饰面 p2/t0 实测复合表头结构(裁剪列位保持): c1 表头空串(真品名列),
# c2='材质/规格' 两列共用的复合词格。修复前 name 锚'材质'占 c2、规格文本被当品名,
# spec 锚因子串也命中 c2 但已被占用 → spec 静默失绑;修复后 name→c1, spec→c2。
_MUSHIMIAN_ROWS = [
    ["序", "", "材质/规格", "计量 单位", "暂定数 量", "不含税 单价", "综合 单价 （含税）", "含税总价", "备 注"],
    ["1", "木饰面", "12mm 燃烧性能等级B1级", "m²", "20167.58", "174.34", "197", "3973013.26", ""],
    ["2", "水磨石浅色光面", "20mm", "m²", "399.03", "228.32", "258", "102949.74", ""],
]


# ── F1a: 标题排除表头行 ──────────────────────────────────────────────────────


def test_collapse_header_returns_header_row_idxs():
    """_collapse_header 第三返回值 = 被合并表头行的索引集合(区别于吞掉的标题行)。

    上浦两级表头: 仅 r0 入合并; r1('规格'单格行)被吞掉但不属于表头行集合。"""
    header, header_rows, hdr_idxs = _collapse_header(_SHANGPU_ROWS)
    assert hdr_idxs == [0]
    assert header_rows == 2  # r0 表头 + r1 吞掉的二级行
    assert "物资名称" in header[0] and "材质" in header[1]


def test_title_text_excludes_only_header_rows():
    """标题文本剔除表头行,但标题行/数据行保留。"""
    rows = [["钢筋供货及价格表"], ["物资名称", "材质"], ["线材", "HPB300Φ8"]]
    assert "钢筋" in _title_text(rows, exclude_rows=[1])  # 标题行仍在
    assert "物资名称" not in _title_text(rows, exclude_rows=[1])  # 表头行已剔除
    assert "物资名称" in _title_text(rows)  # 不传剔除集 = 旧行为


def test_match_seed_title_keyword_not_hijacked_by_column_header():
    """F1a 主回归(上浦): 表头格'物资名称'不再喂给 msm-sc 的标题词'物资',
    sp-gj 以 7 角色(spec→c1)胜出;修复前 msm-sc 靠假标题命中劫持。"""
    seed, roles, header_rows = match_seed(_SHANGPU_ROWS, SEEDS)
    assert seed["id"] == "sp-gj"
    assert roles["name"] == 0
    assert roles["spec"] == 1  # 材质列作规格(修复前 spec 缺失)
    assert roles["price_unit"] == 8 and roles["price_total"] == 9
    assert header_rows == 2


def test_match_seed_title_row_still_counts_after_f1a():
    """F1a 不矫枉过正: 表名标题行(非表头行)里的关键词仍然命中。
    msm-sc 的关键词只出现在标题行(表头/数据行都没有)——若把吞掉的标题行
    一并从标题文本剔除,msm-sc 失去命中而 sp-gj 胜出,此测试即失败。"""
    rows = [
        ["木饰面石材材料清单"],
        ["物资名称", "材质", "计量 单位", "暂定数量", "不含税单价", "综合单价", "含税总价"],
        ["大理石板", "20mm", "m²", "100", "174.34", "197", "19700"],
    ]
    seed, roles, _ = match_seed(rows, SEEDS)
    assert seed["id"] == "msm-sc"


# ── F1b: 复合表头拆分 ────────────────────────────────────────────────────────


def test_match_seed_compound_header_split():
    """F1b 主回归(木饰面): name/spec 同格命中 + 左邻表头空串 → 重绑
    name→c1, spec→c2;extract_items_seed 产出真品名与真规格。"""
    seed, roles, header_rows = match_seed(_MUSHIMIAN_ROWS, SEEDS)
    assert seed["id"] == "msm-sc"
    assert roles["name"] == 1  # 修复前 name→2(规格文本被当品名)
    assert roles["spec"] == 2  # 修复前 spec 静默失绑
    items = extract_items_seed(_MUSHIMIAN_ROWS, seed, roles, header_rows)
    assert [it["name"] for it in items] == ["木饰面", "水磨石浅色光面"]
    assert items[0]["spec"] == "12mm 燃烧性能等级B1级"
    assert items[1]["spec"] == "20mm"


def test_match_seed_compound_header_gate_requires_empty_left_cell():
    """门控单侧不满足不拆: name/spec 同格命中但左邻表头非空串 → 维持原状
    (name 占格、spec 失绑),防把正常窄表拆错。"""
    rows = [
        ["序号", "类别", "材质/规格", "计量 单位", "暂定数量", "不含税单价", "综合单价", "含税总价"],
        ["1", "石材", "20mm", "m²", "100", "174.34", "197", "19700"],
    ]
    seed, roles, _ = match_seed(rows, SEEDS)
    assert seed["id"] == "msm-sc"
    assert roles["name"] == 2
    assert "spec" not in roles  # 左邻'类别'非空 → 不拆


# ── 129 表回放固化回归(容器内全量;宿主机 skip) ───────────────────────────────

_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "seed_hit_replay.json")


def _load_replay_cache():
    """容器内可达时返回 {doc: (tables,...)};宿主机无 OCR 缓存时返回 None(skip)。"""
    try:
        from scripts.config import get_config
        from scripts.document_parser import from_cache
        from scripts.storage import ContractStore

        store = ContractStore(get_config())
        hashes = {
            "上浦钢筋": "5b39470d1678529351ca44272efcb542c55add9e832fe3b176abfb81d2c655a5",
            "木饰面石材": "52bce87cbe9b27441f7a825f16e966b82a9024f261649c6a79d5f3e3c6faea85",
            "砂石料": "9839d01b22ae2cad4dc95f0edb4147b9b836e475727d766e27ba08594aee95b0",
            "钢材签字版": "41ddcdd1e8d8972cf20346cc0fa9c333fb467cd0f2c72e2bcd389b0728a7b1da",
            "钢筋补充协议": "03e28c4c5165124915072af17902a4d7c0e9fa81994948878ce669c13c9107e1",
            "JZGS钢材": "f28c9d26e2803e9437f8ced5c00f99bde396ecbd87aaa1c3251f492326de1bdc",
            "桂北": "1d4331383a733d46ed5760e57aa67be0b8ee11ee0d4b6b5a2fc14621247f14d6",
        }
        caches = {}
        for name, h in hashes.items():
            cache = store.get_ocr_cache(f"ocr/{h}.json")
            if not cache:
                return None
            caches[name] = from_cache(cache)
        return caches
    except Exception:
        return None


def test_replay_129_tables_seed_hit_mapping_frozen():
    """全语料逐表 match_seed 命中映射(seed_id+roles+header_rows)与固化基线逐一相同。

    bug-3428 修复的语料级回归基准: 修复只允许改变 上浦p5/t0(msm-sc→sp-gj)
    与 木饰面p2/t0(name/spec 重绑) 两表,基线即修复后终态。"""
    caches = _load_replay_cache()
    if caches is None:
        pytest.skip("OCR 缓存不可达(容器外宿主机)——129 表回放仅容器内执行")
    baseline = json.load(open(_FIXTURE, encoding="utf-8"))
    seeds = normalize_seeds(DEFAULT_TABLE_SEEDS)  # 与主管线同源,回放才可比
    live_total = 0
    for name, (tables, _, _) in caches.items():
        assert name in baseline, f"基线缺文档 {name}"
        hits = {}
        for t in tables:
            rows = t.rows or []
            if not rows:
                continue
            live_total += 1
            hit = match_seed(rows, seeds)
            key = f"p{t.page_no}/t{t.table_idx}"
            hits[key] = (
                None
                if hit is None
                # roles 序列化成 [role, ci] 列表(与 JSON 固化基线同形)
                else [hit[0]["id"], [[r, c] for r, c in sorted(hit[1].items())], hit[2]]
            )
        assert hits == baseline[name], f"{name} 命中映射偏离固化基线"
    assert live_total == baseline["__total_tables__"] == 129
