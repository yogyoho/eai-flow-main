"""CQ（Competency Questions）验收自动化（F5，2026-10-02 设计 docs/designs/2026-10-02-reasoning-whitebox-plan.md）.

CQ = 可执行验收问题：cq.yaml 每条 {id, question, ask, expect}——ASK 在内核 store 真实
执行，PASS/FAIL 由结果与 expect 比对得出（取代推理工作台页的静态演示判定）。
FAIL 的反事实解释（为什么没推出来）归白盒化 L3 explain-miss（三期），本层先回答
「哪个问题没过」。查询失败不拖垮整批（单条标 error，passed=False）。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from app.ontology.kernel.store import OxStore

CQ_PATH = Path(__file__).parent / "cq.yaml"


@dataclass
class CompetencyQuestion:
    id: str
    question: str
    ask: str  # 自包含 ASK（含 PREFIX / GRAPH 子句）
    expect: bool


def load_cqs(path: Path = CQ_PATH) -> list[CompetencyQuestion]:
    """cq.yaml → CQ 列表（fail-closed：缺字段抛 KeyError/ValueError）。"""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [
        CompetencyQuestion(
            id=str(item["id"]),
            question=str(item["question"]),
            ask=str(item["ask"]),
            expect=bool(item.get("expect", True)),
        )
        for item in data.get("cqs", [])
    ]


def run_cqs(store: OxStore, cqs: list[CompetencyQuestion] | None = None) -> list[dict]:
    """逐条 ASK 真跑 → [{id, question, expected, actual, passed, error?}]。"""
    if cqs is None:
        cqs = load_cqs()
    results: list[dict] = []
    for cq in cqs:
        error: str | None = None
        try:
            actual = store.ask(cq.ask)
        except Exception as e:  # noqa: BLE001 - 单条 CQ 失败不拖垮整批
            actual, error = False, str(e)
        row: dict = {
            "id": cq.id,
            "question": cq.question,
            "expected": cq.expect,
            "actual": actual,
            "passed": error is None and actual == cq.expect,
        }
        if error:
            row["error"] = error
        results.append(row)
    return results
