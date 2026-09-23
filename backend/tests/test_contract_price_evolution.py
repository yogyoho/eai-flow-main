"""自进化捕获桥 D-1/D-3（补遗 2026-09-22）: 错误模式分类 + 折叠 upsert + 端点 diff 捕获。"""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

from app.extensions.contract_price import evolution


# --- classify_error_pattern -------------------------------------------------


def test_error_pattern_classes():
    f = evolution.classify_error_pattern
    assert f("", "4404.25") == "missed"  # 漏提
    assert f("4404.25", "") == "cleared"
    assert f("123456", "124356") == "digit-transposed"  # 数字错位
    assert f("4404", "440425") == "digit-split"  # 粘连/断开(数字串包含)
    assert f("44.04", "44.08") == "digit-drift"  # 数字漂移
    assert f("Q235 B", "q235b") == "variant"  # 命名变体(空白/大小写)
    assert f("20mm", "20mm 厚") == "unit-affixed"  # 单位缀
    assert f("电缆", "钢管") == "other"


# --- capture upsert（零触碰: 原生 SQL, 不 import learnings 模块） -------------


class _CaptureSession:
    """记录 SQL 调用的桩 session。"""

    def __init__(self):
        self.executed = []
        self.commits = 0

    async def execute(self, sql, params):
        self.executed.append((str(sql).strip(), params))

    async def commit(self):
        self.commits += 1


def test_capture_insert_params_shape():
    session = _CaptureSession()
    asyncio.run(
        evolution.capture_field_correction(
            session,
            user_id="u-1",
            scope="item",
            field="unit_price",
            old_value=44.04,
            new_value=4404.25,
            doc_hash="abcdef1234567890",
            error_pattern="digit-drift",
        )
    )
    sql, params = session.executed[0]
    assert "ON CONFLICT (user_id, pattern_key) DO UPDATE" in sql
    assert "recurrence_count = agent_learnings.recurrence_count + 1" in sql
    assert params["pattern_key"] == "data.itemfield-unit_price"
    assert params["symptom"] == "itemfield-unit_price"
    assert params["kind"] == "correction" and params["area"] == "data"
    assert "digit-drift" in params["details"] and "doc=abcdef123456" in params["details"]
    assert session.commits == 1


def test_capture_failure_swallowed():
    """表不存在等异常只降级, 绝不向主流程抛错。"""

    class _Broken(_CaptureSession):
        async def execute(self, sql, params):
            raise RuntimeError("agent_learnings missing")

    session = _Broken()
    asyncio.run(
        evolution.capture_field_correction(
            session, user_id="u-1", scope="doc", field="contract_no", old_value="A", new_value="B"
        )
    )  # 不抛即通过
    assert session.commits == 0


# --- 端点 diff 捕获（D-1 / D-3） ---------------------------------------------


def test_update_document_captures_changed_fields(monkeypatch):
    from app.extensions.contract_price import routers

    pre = SimpleNamespace(
        project_name=None, project_location=None, project_no=None,
        contract_no=None, supplier=None, sign_date=None,
    )
    post = SimpleNamespace(
        project_name="桂北数据中心", project_location=None, project_no=None,
        contract_no=None, supplier=None, sign_date=None, file_hash="h" * 64,
    )
    captured = []

    class _DB:
        async def get(self, model, doc_id):
            return pre  # 更新前 pre-image

    async def fake_update_document(db, doc_id, fields):
        return post

    async def fake_capture(session, **kw):
        captured.append(kw)

    monkeypatch.setattr(routers.crud, "update_document", fake_update_document)
    monkeypatch.setattr(routers.evolution, "capture_field_correction", fake_capture)
    resp = asyncio.run(
        routers.update_document(
            uuid4(),
            SimpleNamespace(model_dump=lambda exclude_unset: {"project_name": "桂北数据中心"}),
            db=_DB(),
            current_user=SimpleNamespace(id=uuid4()),
        )
    )
    assert resp is post
    assert len(captured) == 1
    assert captured[0]["scope"] == "doc" and captured[0]["field"] == "project_name"
    assert captured[0]["old_value"] is None and captured[0]["new_value"] == "桂北数据中心"
    assert captured[0]["doc_hash"] == "h" * 64


def test_update_item_captures_value_changes_with_pattern(monkeypatch):
    from app.extensions.contract_price import routers

    pre_item = SimpleNamespace(unit_price=44.04, goods_name="无缝管", spec_model=None, tech_params={})
    post_item = SimpleNamespace(
        unit_price=4404.0, goods_name="无缝管", spec_model="A108", tech_params={},
        document_id=uuid4(),
    )
    doc = SimpleNamespace(file_hash="d" * 64)
    captured = []

    class _DB:
        def __init__(self):
            self.phase = 0

        async def get(self, model, key):
            self.phase += 1
            if model.__name__ == "CpaItem":
                return pre_item
            return doc

    async def fake_update_item(db, item_id, fields):
        return post_item

    async def fake_capture(session, **kw):
        captured.append(kw)

    monkeypatch.setattr(routers.crud, "update_item", fake_update_item)
    monkeypatch.setattr(routers.evolution, "capture_field_correction", fake_capture)
    asyncio.run(
        routers.update_item(
            uuid4(),
            SimpleNamespace(model_dump=lambda exclude_unset: {"unit_price": 4404.0, "spec_model": "A108"}),
            db=_DB(),
            current_user=SimpleNamespace(id=uuid4()),
        )
    )
    by_field = {c["field"]: c for c in captured}
    assert set(by_field) == {"unit_price", "spec_model"}
    assert by_field["unit_price"]["error_pattern"] == "digit-split"  # 44.04→4404.0 小数点丢失
    assert by_field["spec_model"]["error_pattern"] == "missed"
    assert by_field["unit_price"]["doc_hash"] == "d" * 64


def test_update_item_no_value_change_no_capture(monkeypatch):
    from app.extensions.contract_price import routers

    pre_item = SimpleNamespace(unit_price=10.0, goods_name="A", spec_model=None, tech_params={})
    post_item = SimpleNamespace(unit_price=10.0, goods_name="A", spec_model=None, tech_params={}, document_id=uuid4())
    captured = []

    class _DB:
        async def get(self, model, key):
            if model.__name__ == "CpaItem":
                return pre_item
            return None

    async def fake_update_item(db, item_id, fields):
        return post_item

    async def fake_capture(session, **kw):
        captured.append(kw)

    monkeypatch.setattr(routers.crud, "update_item", fake_update_item)
    monkeypatch.setattr(routers.evolution, "capture_field_correction", fake_capture)
    asyncio.run(
        routers.update_item(
            uuid4(),
            SimpleNamespace(model_dump=lambda exclude_unset: {"validation_status": "ok"}),  # 仅状态采纳, 无值变化
            db=_DB(),
            current_user=SimpleNamespace(id=uuid4()),
        )
    )
    assert captured == []


# --- ⑥ 落地工作流: 候选列表 + 状态流转 ---------------------------------------


class _ListSession:
    """候选列表桩: candidates SQL(.mappings().all()) + 逐条锚词查询(.first())。"""

    def __init__(self, rows, anchor=None):
        self._rows = rows
        self._anchor = anchor

    async def execute(self, sql, params=None):
        s = str(sql)

        class _R:
            def __init__(self, _rows, _first):
                self._rows = _rows
                self._first = _first

            def mappings(self):
                return self

            def all(self):
                return self._rows

            def first(self):
                return self._first

        if "FROM agent_learnings" in s:
            return _R(self._rows, None)
        return _R([], SimpleNamespace(anchors=self._anchor))


def test_list_candidates_parses_evidence_and_anchors():
    row = {
        "id": "lid-1",
        "pattern_key": "data.itemfield-unit_price",
        "recurrence_count": 4,
        "details": "[digit-drift] doc=9839d01b22ae Decimal('202.50') -> 200.0",
        "first_seen_at": "t1",
        "last_seen_at": "t2",
    }
    out = asyncio.run(
        evolution.list_candidates(_ListSession([row], anchor='{"spec": ["规格型号"]}'))
    )
    assert len(out) == 1
    c = out[0]
    assert c["learning_id"] == "lid-1"
    assert c["scope"] == "item" and c["field"] == "unit_price"
    assert c["error_pattern"] == "digit-drift"
    assert c["recurrence"] == 4
    assert "Decimal('202.50')" in c["evidence"]
    assert c["suggested_anchors"]["spec"] == ["规格型号"]


def test_set_candidate_status_validates_and_updates():
    executed = []

    class _R:
        rowcount = 1

    class _S:
        async def execute(self, sql, params):
            executed.append(params)

            class _R2:
                rowcount = 1

            return _R2()

        async def commit(self):
            pass

    assert asyncio.run(evolution.set_candidate_status(_S(), "lid-1", "promoted_to_skill")) is True
    assert executed[0]["status"] == "promoted_to_skill"
    assert asyncio.run(evolution.set_candidate_status(_S(), "lid-1", "bogus")) is False


def test_list_candidates_tolerates_leading_space_in_details():
    """真机抓过: details 前导空格曾使 error_pattern/doc 解析为空。"""
    row = {
        "id": "lid-2",
        "pattern_key": "data.docfield-contract_no",
        "recurrence_count": 2,
        "details": " [digit-drift] doc=9839d01b22ae None -> '2GS-YCXM-CL-CG-024-2019'",
        "first_seen_at": "t1",
        "last_seen_at": "t2",
    }
    out = asyncio.run(evolution.list_candidates(_ListSession([row])))
    c = out[0]
    assert c["scope"] == "doc" and c["field"] == "contract_no"
    assert c["error_pattern"] == "digit-drift"
    assert c["doc_hash"] == "9839d01b22ae"
    assert "2GS-YCXM" in c["evidence"]
