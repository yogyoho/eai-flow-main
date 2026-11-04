"""Minor-4 NULL entity_keys 病理(spec 2026-11-04):跑过中间提交 bfde4add6 裸
ALTER 的环境存量行 entity_keys=NULL → IssueOut.model_validate ValidationError
→ issues 端点 500。读路径 validator None→[] 兜底;bootstrap UPDATE 数据归一
(启动自愈,SQL 文本不断言)。"""

from app.extensions.bid_review.schemas import IssueOut


class _ORMIssue:
    """模拟存量 ORM 行(entity_keys 可为 NULL 的裸 ALTER 环境)。"""

    def __init__(self, entity_keys):
        self.id = "i1"
        self.task_id = "t1"
        self.rule_id = "L2-020"
        self.layer = "L2"
        self.severity = "fatal"
        self.verdict = "violation"
        self.clause_id = None
        self.message = "缺少附件"
        self.fix = ""
        self.evidence = []
        self.entity_keys = entity_keys
        self.dedup_key = "k1"
        self.need_human = False
        self.confidence = 1.0
        self.created_at = "2026-11-04T00:00:00+00:00"


def test_entity_keys_null_coerced_to_empty():
    """裸 ALTER 存量行 entity_keys=NULL → 投影 [] 而非 ValidationError(Minor-4)。"""
    out = IssueOut.model_validate(_ORMIssue(None))
    assert out.entity_keys == []


def test_entity_keys_list_passthrough():
    """正常列表透传零改写(兜底不侵蚀既有值)。"""
    out = IssueOut.model_validate(_ORMIssue(["attachment:5"]))
    assert out.entity_keys == ["attachment:5"]
