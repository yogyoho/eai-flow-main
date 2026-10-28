"""Task 6 测试:bid_review 五张表注册 + 关键列 + A8 列宽约束。"""

from app.extensions.bid_review.models import (
    BaselinePackage,
    ReviewFeedback,
    ReviewIssue,
    ReviewTask,
    RulePackMeta,
)


def test_tables_registered():
    assert ReviewTask.__tablename__ == "bid_review_tasks"
    assert ReviewIssue.__tablename__ == "bid_review_issues"
    assert BaselinePackage.__tablename__ == "bid_review_baselines"
    assert RulePackMeta.__tablename__ == "bid_review_rulepacks"
    assert ReviewFeedback.__tablename__ == "bid_review_feedback"
    cols = {c.name for c in ReviewTask.__table__.columns}
    assert {"id", "owner_id", "status", "mode", "progress", "error", "engine_meta", "prev_task_id", "created_at"} <= cols
    icols = {c.name for c in ReviewIssue.__table__.columns}
    assert {"id", "task_id", "rule_id", "layer", "severity", "verdict", "message", "fix", "evidence", "dedup_key", "need_human", "confidence", "created_at"} <= icols


def test_other_tables_key_columns():
    bcols = {c.name for c in BaselinePackage.__table__.columns}
    assert {"id", "task_id", "kind", "payload", "confirmed", "created_at"} <= bcols
    rcols = {c.name for c in RulePackMeta.__table__.columns}
    assert {"id", "name", "version", "stats", "enabled"} <= rcols
    fcols = {c.name for c in ReviewFeedback.__table__.columns}
    assert {"id", "issue_id", "owner_id", "action", "new_severity", "note", "created_at"} <= fcols


def test_a8_verdict_and_action_string20():
    """A8:false_positive=14 / severity_change=15 溢出 String(12);PostgreSQL 超宽报错不截断。"""
    assert ReviewIssue.__table__.columns["verdict"].type.length == 20
    assert ReviewFeedback.__table__.columns["action"].type.length == 20
