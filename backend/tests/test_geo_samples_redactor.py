"""两档脱敏规则引擎：auto=替换****、review=只标记；地质数值永不脱敏。"""

from app.extensions.geo_samples.redactor import MASK, redact_text


def test_auto_replaces_cert_and_coords():
    md = "探矿权证号C5300002023000001，坐标 X 3546123.45, Y 38456789.12。\n联系电话13812345678。"
    clean, events = redact_text(md)
    assert "C5300002023000001" not in clean
    assert MASK in clean
    assert "13812345678" not in clean
    rules = {e["rule"] for e in events if e["replaced"]}
    assert "exploration_cert" in rules
    assert "coord_pair" in rules
    assert "phone" in rules


def test_review_mode_flags_but_does_not_replace():
    md = "项目负责人：张三丰"
    clean, events = redact_text(md)
    assert "张三丰" in clean  # 不替换
    assert any(e["rule"] == "person_field" and not e["replaced"] for e in events)


def test_geo_numbers_never_redacted():
    """红线：品位/厚度/资源量等地质数值必须原样保留（东川样例口径）。"""
    md = "平均品位0.85%，最小可采厚度1.00m，资源量77.36万吨，涌水量11850m3/d。"
    clean, events = redact_text(md)
    assert clean == md
    assert events == []


def test_events_record_hash_not_plaintext():
    import hashlib

    _, events = redact_text("证号C5300002023000002")
    e = events[0]
    assert e["original_hash"] == hashlib.sha256(b"C5300002023000002").hexdigest()
    assert "C5300002023000002" not in str(e)


def test_overlapping_matches_keep_first():
    md = "云南XX勘查院有限公司"
    clean, events = redact_text(md)
    assert "云南" in clean or MASK in clean  # 不崩溃即可；重叠命中只记一条
    assert len([e for e in events if e["replaced"]]) == 1
