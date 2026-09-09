# EAI-CUSTOM: 煤矿环评报告样例库 二期（BS3 ④质检面板 MVP）——六项质检 + 打分 + 全库聚合。
# 质检基于台账已有字段与 outline_json（提取流水线产物）：能查则查，缺数据记 unknown（不臆断）。
"""Quality checks for the coal EIA sample bank (phase 2).

Six checks per sample (file_hash / content-outline / scenario enum / duplicate
title / privacy scan / chapter numbering), each returning pass|warn|fail|unknown
plus a 0-100 score. ``QualityService.summarize`` aggregates the whole library.
"""

import re

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .extract import outline_text_for_scan
from .models import KFSample
from .schemas import SampleScenario

# 检查项 id（前端徽章与聚合 by_result 以此对齐）
CHECK_IDS = ("file_hash", "content_outline", "scenario_enum", "duplicate_title", "privacy_scan", "chapter_numbering")

RESULT_WEIGHTS = {"pass": 1.0, "warn": 0.6, "unknown": 0.5, "fail": 0.0}

_HASH_RE = re.compile(r"^[0-9a-f]{8,64}$")
_HASH_RE_LOOSE = re.compile(r"^[0-9A-Fa-f]{8,64}$")
# 隐私扫描：18 位身份证 / 手机号 / "身份证" 关键词（扫 outline_json 文本化 + notes）
_PRIVACY_ID = re.compile(r"\d{17}[\dXx]")
_PRIVACY_PHONE = re.compile(r"1[3-9]\d{9}")
_PRIVACY_KEYWORD = "身份证"
# 编号体检：跳号/重号检查的最少章数（<2 无法判定连续性）
_MIN_CHAPTERS_FOR_CONTINUITY = 2


def _mask(number: str) -> str:
    """隐私数字脱敏展示（前6后2，中段打码）——detail 里不回传完整号码。"""
    return number[:6] + "****" + number[-2:] if len(number) > 8 else "****"


class QualityService:
    """样例质检：单样例六项检查 + 全库聚合（质检面板数据源）"""

    @staticmethod
    def run_checks(sample: KFSample, title_counts: dict[str, int]) -> list[dict]:
        """六项质检。title_counts = 全库 title→行数 映射（service 层一次 group-by 传入）。"""
        checks: list[dict] = []

        def add(check: str, result: str, detail: str) -> None:
            checks.append({"check": check, "result": result, "detail": detail})

        # 1. file_hash 在场且格式合法（64 位小写十六进制为规范形；大写/异常长度记 warn）
        file_hash = sample.file_hash or ""
        if not file_hash:
            add("file_hash", "fail", "file_hash 缺失")
        elif _HASH_RE.match(file_hash):
            add("file_hash", "pass", f"哈希格式合法（{len(file_hash)} 位十六进制）")
        elif _HASH_RE_LOOSE.match(file_hash):
            add("file_hash", "warn", "哈希含大写字母或长度不在 8-64 规范区间（建议统一小写 SHA-256）")
        else:
            add("file_hash", "warn", "哈希格式异常（非十六进制串）")

        # 2. content/outline 非空（依据 outline_json；无 content 字段的登记行记 unknown）
        outline = sample.outline_json if isinstance(sample.outline_json, dict) else None
        chapters = (outline or {}).get("chapters") or []
        if outline is None:
            add("content_outline", "unknown", "尚未运行提取流水线，无 content/outline 数据")
        elif chapters:
            add("content_outline", "pass", f"大纲非空（{len(chapters)} 章）")
        else:
            add("content_outline", "warn", "outline_json 在场但未提取到章节")

        # 3. scenario 枚举合法
        valid_scenarios = {s.value for s in SampleScenario}
        if sample.scenario in valid_scenarios:
            add("scenario_enum", "pass", f"scenario={sample.scenario}")
        else:
            add("scenario_enum", "fail", f"scenario={sample.scenario!r} 不在合法枚举内")

        # 4. 重复标题（全库同 title）
        dup = title_counts.get(sample.title or "", 0)
        if dup > 1:
            add("duplicate_title", "warn", f"全库存在 {dup} 条同题样例（标题重复，疑似同文件多登记或版本族未标注 variant）")
        else:
            add("duplicate_title", "pass", "标题全库唯一")

        # 5. 隐私扫描（身份证号/手机号/关键词；无文本可扫记 unknown）
        scan_text = (sample.notes or "") + "\n" + (outline_text_for_scan(outline) if outline else "")
        if not scan_text.strip():
            add("privacy_scan", "unknown", "无可扫描文本（未提取且无备注）")
        else:
            hits: list[str] = []
            ids = _PRIVACY_ID.findall(scan_text)
            if ids:
                hits.append(f"疑似身份证号 ×{len(ids)}（如 {_mask(ids[0])}）")
            # 身份证命中段先抹掉再扫手机号（18 位号会内含 1[3-9]\d{9} 误报）
            residue = _PRIVACY_ID.sub("0" * 18, scan_text)
            phones = _PRIVACY_PHONE.findall(residue)
            if phones:
                hits.append(f"疑似手机号 ×{len(phones)}（如 {_mask(phones[0])}）")
            if _PRIVACY_KEYWORD in scan_text:
                hits.append('含关键词"身份证"')
            if hits:
                add("privacy_scan", "fail", "隐私命中：" + "；".join(hits))
            else:
                add("privacy_scan", "pass", "未命中隐私模式")

        # 6. 编号体检（章号连续性：1,2,4,5 → 报缺 3；取阿拉伯/中文两族中多数族判定）
        no_ints = [c.get("no_int") for c in chapters if isinstance(c, dict)]
        no_ints = [n for n in no_ints if isinstance(n, int)]
        if not chapters:
            add("chapter_numbering", "unknown", "无章节数据，无法体检编号")
        elif len(no_ints) < _MIN_CHAPTERS_FOR_CONTINUITY:
            add("chapter_numbering", "unknown", f"可判定的数字章号少于 {_MIN_CHAPTERS_FOR_CONTINUITY} 个（{len(no_ints)} 个）")
        else:
            expected = set(range(min(no_ints), max(no_ints) + 1))
            missing = sorted(expected - set(no_ints))
            dupes = sorted({n for n in no_ints if no_ints.count(n) > 1})
            problems: list[str] = []
            if missing:
                problems.append("章号跳号，缺 " + "、".join(str(n) for n in missing))
            if dupes:
                problems.append("章号重号 " + "、".join(str(n) for n in dupes))
            if problems:
                add("chapter_numbering", "warn", "；".join(problems))
            else:
                add("chapter_numbering", "pass", f"章号 {min(no_ints)}-{max(no_ints)} 连续无缺")
        return checks

    @staticmethod
    def score_of(checks: list[dict]) -> int:
        """0-100：pass=1 / warn=0.6 / unknown=0.5 / fail=0 等权平均。"""
        if not checks:
            return 0
        return round(100 * sum(RESULT_WEIGHTS.get(c["result"], 0.0) for c in checks) / len(checks))

    @staticmethod
    def worst_result(checks: list[dict]) -> str:
        """样例整体最差结果（fail > warn > unknown > pass），聚合排序用。"""
        order = {"fail": 0, "warn": 1, "unknown": 2, "pass": 3}
        return min((c["result"] for c in checks), key=lambda r: order.get(r, 4)) if checks else "pass"

    @staticmethod
    async def title_counts(db: AsyncSession) -> dict[str, int]:
        """全库 title→行数（重复标题检测用，一次 group-by）。"""
        rows = await db.execute(select(KFSample.title, func.count()).group_by(KFSample.title))
        return {title: cnt for title, cnt in rows.all()}

    @staticmethod
    def report_for(sample: KFSample, title_counts: dict[str, int]) -> dict:
        """单样例质检报告：{sample_id, title, scenario, checks, score}。"""
        checks = QualityService.run_checks(sample, title_counts)
        return {
            "sample_id": sample.id,
            "title": sample.title,
            "scenario": sample.scenario,
            "checks": checks,
            "score": QualityService.score_of(checks),
        }

    @staticmethod
    async def summarize(db: AsyncSession, items_limit: int = 50) -> dict:
        """全库聚合：{total, by_result, by_scenario, items[前 limit 按分数升序=最差优先]}。"""
        samples = (await db.execute(select(KFSample).order_by(KFSample.created_at.desc()))).scalars().all()
        counts = await QualityService.title_counts(db)
        by_result = {r: 0 for r in ("pass", "warn", "fail", "unknown")}
        by_scenario: dict[str, dict] = {}
        items: list[dict] = []
        for s in samples:
            checks = QualityService.run_checks(s, counts)
            score = QualityService.score_of(checks)
            for c in checks:
                by_result[c["result"]] = by_result.get(c["result"], 0) + 1
            agg = by_scenario.setdefault(s.scenario, {"samples": 0, "score_sum": 0})
            agg["samples"] += 1
            agg["score_sum"] += score
            items.append(
                {
                    "sample_id": s.id,
                    "title": s.title,
                    "scenario": s.scenario,
                    "score": score,
                    "worst_result": QualityService.worst_result(checks),
                    "problems": [f"{c['check']}: {c['detail']}" for c in checks if c["result"] in ("warn", "fail")],
                }
            )
        items.sort(key=lambda it: (it["score"], it["title"]))
        return {
            "total": len(samples),
            "by_result": by_result,
            "by_scenario": {sc: {"samples": a["samples"], "avg_score": round(a["score_sum"] / a["samples"], 1) if a["samples"] else 0.0} for sc, a in by_scenario.items()},
            "items": items[:items_limit],
        }
