"""Unit tests for knowledge_factory pipeline helpers.

Focus: chunk-based chapter heading scan + noise filter. These run without
external services (no RAGFlow, no DB, no LLM).
"""

from app.extensions.knowledge_factory.pipeline import _is_noise

# ── _is_noise: 子句标点守卫 (bug-404) ──


def test_is_noise_rejects_clause_punctuation_body():
    """3218 掘进规程里被误判为章节的正文段（含子句/句末标点）应被判为噪音，
    不进入 chunk 版 structure_hint 的章节目录。"""
    assert _is_noise("（4）遇顶板巷帮岩体破碎、巷道成型差时，顶板支护时，根据现场实际情况") is True
    assert _is_noise("②掘进巷道回风流甲烷传感器处安设1路摄像仪，监视回风流甲烷传感器的运行情况。") is True
    assert _is_noise("26、对应力集中区（向斜和背斜轴部）用锚杆钻机探测一次顶板岩性，并增加一组") is True
    assert _is_noise("8、工作面积水、巷中积水严禁上输送机，生产过程中开机开水") is True
    assert _is_noise("2、掘进中涉及的开口、拐弯时，需对开口处补强") is True


def test_is_noise_passes_real_chapter_titles():
    """真章节标题（名词短语，无子句标点）不应被判为噪音。"""
    assert _is_noise("概况") is False
    assert _is_noise("地面位置及地质情况") is False
    assert _is_noise("巷道布置及支护说明") is False
    assert _is_noise("施工工艺") is False
    assert _is_noise("生产系统") is False
    assert _is_noise("劳动组织及主要技术经济指标") is False
    assert _is_noise("灾害应急措施及避灾路线") is False
    assert _is_noise("第一章 总则") is False


def test_is_noise_still_catches_existing_cases():
    """原有噪音判定（问卷项、问号）不应回归。"""
    assert _is_noise("1、您了解本项目的环境影响吗？") is True
    assert _is_noise("2、噪声：合理布局，噪声高的设备需要采用低噪声设备") is True


# ── _nest_by_level: 平铺 level 列表 → 树 (bug-1241 目录扁平化) ──
from app.extensions.knowledge_factory.pipeline import _nest_by_level  # noqa: E402


def _flat(levels):
    return [{"id": f"sec_{i + 1:02d}", "title": f"t{i + 1}", "level": lv, "required": True} for i, lv in enumerate(levels)]


def test_nest_by_level_basic_three_level():
    """1,2,1,2,3 → 两棵树，子节挂到对应父节下。"""
    tree = _nest_by_level(_flat([1, 2, 1, 2, 3]))
    assert [s["title"] for s in tree] == ["t1", "t3"]
    assert [c["title"] for c in tree[0]["children"]] == ["t2"]
    assert tree[1]["children"][0]["children"][0]["title"] == "t5"


def test_nest_by_level_skip_level_attaches_to_shallower():
    """level 跳级 1→3：挂到最近的更浅节点（level 1）下，不悬空。"""
    tree = _nest_by_level(_flat([1, 3]))
    assert len(tree) == 1
    assert tree[0]["children"][0]["level"] == 3


def test_nest_by_level_leading_deep_heading_becomes_root():
    """首个标题就是 level 2（无上级）：作为根返回，不丢。"""
    tree = _nest_by_level(_flat([2, 2]))
    assert len(tree) == 2
    assert all("children" not in s for s in tree)


def test_nest_by_level_roundtrip_flatten():
    """与 _flatten_sections 互逆：树展平后顺序与原平铺一致。"""
    from app.extensions.knowledge_factory.pipeline import _flatten_sections

    levels = [1, 2, 1, 2, 3, 3, 1, 2]
    tree = _nest_by_level(_flat(levels))
    assert [s["level"] for s in _flatten_sections(tree)] == levels


def test_nest_by_level_strips_empty_children():
    """叶子节点不应残留空 children 数组。"""
    tree = _nest_by_level(_flat([1, 1]))
    assert all("children" not in s for s in tree)


# ── bug-1242: 兜底标题源优先 _parsed + 扫描加固（目录页码粘连 / （N）降级） ──
from types import SimpleNamespace  # noqa: E402

from app.extensions.knowledge_factory.pipeline import (  # noqa: E402
    _auto_headings,
    _scan_chapter_headings,
)


def _chunks(*lines):
    return [{"content": "\n\n".join(lines)}]


def test_auto_headings_prefers_parsed_headings():
    """_parsed.headings 存在时必须优先（Word 样式可靠、无目录行），而非重扫 chunk 文本。"""
    doc = {
        "_parsed": SimpleNamespace(
            headings=[
                SimpleNamespace(title="1绪论", level=1),
                SimpleNamespace(title="2 区域地质", level=1),
            ]
        )
    }
    # chunk 文本里故意放目录粘连行——若走了扫描分支就会出现粘尾页码
    chunks = _chunks("1.5.1 以往工作评述5", "2 区域地质13")
    out = _auto_headings(doc, chunks)
    assert [h["title"] for h in out] == ["1绪论", "2 区域地质"]
    assert [h["level_guess"] for h in out] == [1, 1]


def test_auto_headings_falls_back_to_scan_without_parsed():
    """无 _parsed 时退回文本扫描——旧行为兜底仍可用。"""
    out = _auto_headings({}, _chunks("2 区域地质"))
    assert [h["title"] for h in out] == ["2 区域地质"]


def test_scan_strips_toc_page_number_when_twin_exists():
    """目录粘连行（页码粘尾、无 tab/多空格）与正文标题共存时归一去重为一份。"""
    out = _scan_chapter_headings(_chunks("1.5.1 以往工作评述5", "1.5.2 矿山设计、开采和资源利用概况8", "正文段不计。", "1.5.1 以往工作评述", "1.5.2 矿山设计、开采和资源利用概况"))
    titles = [h["title"] for h in out]
    assert titles.count("1.5.1 以往工作评述") == 1
    assert titles.count("1.5.2 矿山设计、开采和资源利用概况") == 1
    assert not any(t.endswith("5") and t != "1.5.1 以往工作评述" for t in titles)


def test_scan_keeps_digit_ending_title_without_twin():
    """无孪生（正文标题不存在）时不得改写——合法以数字结尾的标题保留原样。"""
    out = _scan_chapter_headings(_chunks("8.10 伴生矿产的资源估算方法及结果122"))
    assert [h["title"] for h in out] == ["8.10 伴生矿产的资源估算方法及结果122"]


def test_scan_demotes_paren_items_after_numbered_l2():
    """x.y 编号出现后的（N）条目降为 level 3，不再与 x.y 同层。"""
    out = _scan_chapter_headings(_chunks("2 区域地质", "2.1 区域地质特征", "（1）褶皱", "（2）断裂"))
    levels = {h["title"]: h["level_guess"] for h in out}
    assert levels["2 区域地质"] == 1
    assert levels["2.1 区域地质特征"] == 2
    assert levels["（1）褶皱"] == 3
    assert levels["（2）断裂"] == 3


def test_scan_keeps_paren_items_without_numbered_l2():
    """纯 第X章+（一） 式文档（无 x.y 编号）中（N）保持 level 2。"""
    out = _scan_chapter_headings(_chunks("第一章 总则", "（一）背景"))
    levels = {h["title"]: h["level_guess"] for h in out}
    assert levels["（一）背景"] == 2
