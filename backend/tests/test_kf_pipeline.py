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
