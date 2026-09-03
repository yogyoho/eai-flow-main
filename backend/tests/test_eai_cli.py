"""统一 CLI（tools/eai.py）单元测试——importlib 加载，httpx.MockTransport/fake 会话假网络。"""

import csv
import importlib.util
import sys
import types
from pathlib import Path

import httpx
import pytest

CLI_PATH = Path(__file__).resolve().parents[2] / "tools" / "eai.py"
spec = importlib.util.spec_from_file_location("eai_cli", CLI_PATH)
eai = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eai)


def test_login_and_probe_contract():
    """登录拿双 cookie → csrf 头回填 → /api/v1/auth/me 200 探活。"""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path, request.headers))
        if request.url.path == "/api/extensions/auth/login":
            return httpx.Response(
                200,
                json={"expires_in": 86400, "needs_setup": False},
                headers=[("set-cookie", "access_token=jwt123; Path=/"), ("set-cookie", "csrf_token=tok456; Path=/")],
            )
        if request.url.path == "/api/v1/auth/me":
            assert request.headers["cookie"].count("access_token=jwt123")
            return httpx.Response(200, json={"id": "u1"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    sess = eai.login("http://x", "admin@eai-flow.com", "Admin@2026", transport=transport)
    assert sess.csrf == "tok456"
    assert eai.probe(sess, transport=transport) is True
    # 状态变更请求自动带 X-CSRF-Token（transport 注入只在 login/probe 构造期）
    sess.post("http://x/api/extensions/geo-samples/documents/d1/parse")
    m, p, h = calls[-1]
    assert h["X-CSRF-Token"] == "tok456"


def test_login_429_respects_lockout():
    def handler(request):
        return httpx.Response(429, json={"detail": "Too many login attempts. Try again later."})

    with pytest.raises(eai.LoginLocked):
        eai.login("http://x", "u", "p", transport=httpx.MockTransport(handler))


def test_password_env_fallback(monkeypatch):
    """EAI_PASSWORD 设置时 --password 可省；未设时 argparse required 拦截（SystemExit 2）。"""

    @eai.register("pwenv", "smoke")
    def cmd_pwenv(sess, args):
        return 0

    argv = ["pwenv", "--username", "u"]
    monkeypatch.setenv("EAI_PASSWORD", "envpw")
    args = eai.build_parser().parse_args(argv)
    assert args.password == "envpw"
    monkeypatch.delenv("EAI_PASSWORD")
    with pytest.raises(SystemExit) as e:
        eai.build_parser().parse_args(argv)
    assert e.value.code == 2


def test_group_command_creds_at_leaf(monkeypatch):
    """嵌套组命令（gsb）凭据必须能放在 leaf 子命令之后——argparse 父级选项须在子命令名前，
    而 `eai.py gsb scan --dir X --username u` 是计划文档规定的自然调用位置。"""
    monkeypatch.delenv("EAI_PASSWORD", raising=False)
    args = eai.build_parser().parse_args(["gsb", "scan", "--dir", "/tmp", "--username", "u", "--password", "p"])
    assert args.username == "u" and args.password == "p" and args.dir == "/tmp"
    args2 = eai.build_parser().parse_args(["cpa", "upload", "--dir", "/tmp", "--username", "u", "--password", "p"])
    assert args2.username == "u" and args2.dir == "/tmp"


def test_main_error_surface(monkeypatch, capsys):
    """main 顶层错误面：LoginLocked rc=3；认证 401 rc=3；均人话 stderr 不裸 traceback。"""

    @eai.register("errsurf", "smoke")
    def cmd_errsurf(sess, args):
        return 0

    monkeypatch.setattr(eai, "login", lambda *a, **k: (_ for _ in ()).throw(eai.LoginLocked("桶满")))
    assert eai.main(["errsurf", "--username", "u", "--password", "p"]) == 3
    assert "登录限流" in capsys.readouterr().err

    req = httpx.Request("POST", "http://x/login")
    monkeypatch.setattr(
        eai,
        "login",
        lambda *a, **k: (_ for _ in ()).throw(httpx.HTTPStatusError("401", request=req, response=httpx.Response(401, request=req))),
    )
    assert eai.main(["errsurf", "--username", "u", "--password", "p"]) == 3
    assert "登录失败: 401" in capsys.readouterr().err


# --- T6: gsb scan/import + license generate ----------------------------------


def test_gsb_scan_rows(tmp_path):
    """scan 纯函数：目录文件 → suggest_fn → 行生成 + 置信度 + 文件对应（题名=文件名去扩展）。"""

    def fake_suggest(title):
        if "铜矿" in title:
            return {
                "region": "云南省昆明市东川区",
                "mineral": "copper",
                "stage": "exploration",
                "confidence": "auto",
                "report_id": "gsb-kc-cu-0001",
            }
        return {"region": None, "mineral": None, "stage": None, "confidence": "needs-review", "report_id": "gsb-auto-0001"}

    (tmp_path / "云南省昆明市东川区某铜矿勘探报告.docx").write_bytes(b"x")
    (tmp_path / "无规律文件.docx").write_bytes(b"y")
    rows = eai.gsb_scan_rows(tmp_path, fake_suggest, limit=10)
    assert len(rows) == 2
    assert rows[0]["file_name"] == "云南省昆明市东川区某铜矿勘探报告.docx"
    assert rows[0]["report_id"] == "gsb-kc-cu-0001" and rows[0]["confidence"] == "auto"
    assert rows[1]["file_name"] == "无规律文件.docx"
    assert rows[1]["confidence"] == "needs-review"


def test_gsb_scan_conflict_bump(tmp_path):
    """同组建议 id 冲突顺延：第二次出现起序号递增重写，且不被 CSV 外键污染。"""

    def fake_suggest(_title):
        return {"region": None, "mineral": None, "stage": None, "confidence": "needs-review", "report_id": "gsb-auto-0001"}

    (tmp_path / "a报告.docx").write_bytes(b"x")
    (tmp_path / "b报告.docx").write_bytes(b"y")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c报告.pdf").write_bytes(b"z")
    rows = eai.gsb_scan_rows(tmp_path, fake_suggest, recursive=True)
    assert [r["report_id"] for r in rows] == ["gsb-auto-0001", "gsb-auto-0002", "gsb-auto-0003"]
    assert sum(1 for r in rows if r.get("_conflict")) == 2  # 内部计数键，不进 CSV 列


def test_import_state_resume(tmp_path):
    """断点 state：mark_done 即写盘 → 新实例（模拟重跑进程）is_done 命中。"""
    state_path = tmp_path / "gsb_manifest.state.json"
    state = eai.ImportState(state_path)
    assert not state.is_done("gsb-kc-cu-0001")
    state.mark_done("gsb-kc-cu-0001")
    assert state.is_done("gsb-kc-cu-0001")
    assert state_path.exists()
    state2 = eai.ImportState(state_path)
    assert state2.is_done("gsb-kc-cu-0001")
    assert not state2.is_done("gsb-kc-cu-0002")


def test_import_409_bumps_sequence(tmp_path):
    """409 撞号（detail 含「已存在」）→ report_id 序号 +1 重试；成功后非 defer 再触发 parse。"""
    upload_data = []
    parse_calls = []

    class FakeSess:
        """bump_first=True：首呼撞号 409、次呼成功；False：直呼成功（有状态 fake 不跨用例复用）。"""

        def __init__(self, bump_first=True):
            self.bump_first = bump_first
            self.calls = 0

        def post(self, path, files=None, data=None, **kw):
            if path.endswith("/parse"):
                parse_calls.append(path)
                return httpx.Response(200, json={"run_id": "pr"})
            upload_data.append(dict(data))
            self.calls += 1
            if self.calls == 1 and self.bump_first:
                return httpx.Response(409, json={"detail": "report_id gsb-kc-cu-0001 已存在"})
            return httpx.Response(200, json={"document": {"id": "d9", "report_id": data["report_id"]}, "run_id": "r"})

    row = {
        "file_name": "a.docx",
        "report_id": "gsb-kc-cu-0001",
        "stage": "exploration",
        "mineral": "copper",
        "region": "",
        "confidence": "auto",
    }
    f = tmp_path / "a.docx"
    f.write_bytes(b"x")
    result = eai.upload_one(FakeSess(), str(f), row, defer_parse=False)
    assert result["report_id"] == "gsb-kc-cu-0002" and result["document_id"] == "d9"
    assert [d["report_id"] for d in upload_data] == ["gsb-kc-cu-0001", "gsb-kc-cu-0002"]
    assert "region" not in upload_data[0]  # 空值字段不透传（非空才带）
    assert parse_calls == ["/api/extensions/geo-samples/documents/d9/parse"]

    parse_calls.clear()
    result2 = eai.upload_one(FakeSess(bump_first=False), str(f), row, defer_parse=True)  # 首呼即 200
    assert result2["report_id"] == "gsb-kc-cu-0001" and parse_calls == []  # defer 时不触发 parse


def test_upload_one_defer_parse_passthrough(tmp_path):
    """defer_parse=True → multipart data 含 defer_parse=true 且成功后不调 parse。"""
    f = tmp_path / "a.docx"
    f.write_bytes(b"x")
    posts = []

    class FakeSess:
        def post(self, path, files=None, data=None, **kw):
            posts.append((path, data))
            if path.endswith("/upload"):
                return httpx.Response(200, json={"document": {"id": "d1", "report_id": data["report_id"]}}, request=httpx.Request("POST", path))
            return httpx.Response(409, json={"detail": "解析任务已在跑"}, request=httpx.Request("POST", path))

    row = {"file_name": "a.docx", "report_id": "gsb-kc-cu-0001", "stage": "exploration", "mineral": "copper", "region": "", "confidence": "auto"}
    result = eai.upload_one(FakeSess(), str(f), row, defer_parse=True)
    assert result["report_id"] == "gsb-kc-cu-0001"
    up_data = posts[0][1]
    assert up_data["defer_parse"] == "true"
    assert len([p for p, _ in posts if p.endswith("/parse")]) == 0  # 不再发幂等 parse


def test_cmd_gsb_import_mixed(tmp_path, capsys):
    """cmd 编排（T6 review Important-2）：1 成功 + 1 连接异常 → rc=1、failed CSV 含失败行原内容
    +错误列、state 只含成功 rid（失败行不得进断点，重跑须可重试）。"""
    ok_row = {"file_name": "a.docx", "report_id": "gsb-kc-cu-0001", "stage": "exploration", "mineral": "copper", "region": "", "confidence": "auto"}
    bad_row = {"file_name": "b.docx", "report_id": "gsb-auto-0001", "stage": "", "mineral": "", "region": "", "confidence": "needs-review"}

    class Sess:
        def post(self, path, files=None, data=None, **kw):
            req = httpx.Request("POST", "http://x" + path)
            if path.endswith("/documents/upload"):
                if data["report_id"] == "gsb-kc-cu-0001":
                    return httpx.Response(200, json={"document": {"id": "d1", "report_id": data["report_id"]}, "run_id": "r"}, request=req)
                raise httpx.ConnectError("connection refused")  # 网络故障——单行失败不拖垮整批
            if path.endswith("/parse"):
                return httpx.Response(200, json={"run_id": "pr"}, request=req)
            raise AssertionError(path)

    root = tmp_path
    (root / "a.docx").write_bytes(b"x")
    (root / "b.docx").write_bytes(b"y")
    csv_path = root / "gsb_manifest.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=["file_name", "report_id", "stage", "mineral", "region", "confidence"])
        writer.writeheader()
        writer.writerows([ok_row, bad_row])
    args = eai.build_parser().parse_args(["gsb", "import", "--csv", str(csv_path), "--dir", str(root), "--username", "u", "--password", "p"])
    rc = eai.cmd_gsb_import(Sess(), args)
    assert rc == 1
    out = capsys.readouterr().out  # readouterr 消费缓冲——只调一次
    assert "上传 1 成功" in out and "失败 1" in out
    state = eai.ImportState(root / "gsb_manifest.state.json")
    assert state.is_done("gsb-kc-cu-0001") and not state.is_done("gsb-auto-0001")  # state 只含成功 rid
    failed_csv = (root / "gsb_import_failed.csv").read_text(encoding="utf-8-sig")
    assert "gsb-auto-0001" in failed_csv and "b.docx" in failed_csv
    assert "error" in failed_csv and "connection refused" in failed_csv  # 原行内容 + 错误列


def test_cmd_cpa_upload_flow(tmp_path, capsys):
    """cmd 编排（T6 review Important-2）：3 文件（成功/409 内容重复/HTTPError）+ --trigger-parse →
    pipeline/run 恰调 1 次、409 计 skipped、异常计失败 rc=1。"""
    calls = []

    class Sess:
        def post(self, path, files=None, data=None, json=None, **kw):
            req = httpx.Request("POST", "http://x" + path)
            calls.append((path, json))
            if path.endswith("/documents/upload"):
                name = files["file"][0]
                if name == "dup.pdf":
                    return httpx.Response(409, json={"detail": "该合同内容已存在(文件名: x.pdf)"}, request=req)
                if name == "boom.pdf":
                    raise httpx.ConnectError("connection reset")
                return httpx.Response(200, json={"storage_uri": "s3://b/k", "file_name": name, "size": 1}, request=req)
            if path.endswith("/pipeline/run"):
                return httpx.Response(200, json={"run_id": "run1", "status": "running", "message": "parse started"}, request=req)
            raise AssertionError(path)

    root = tmp_path
    (root / "good.pdf").write_bytes(b"1")
    (root / "dup.pdf").write_bytes(b"2")
    (root / "boom.pdf").write_bytes(b"3")
    args = eai.build_parser().parse_args(["cpa", "upload", "--dir", str(root), "--trigger-parse", "--username", "u", "--password", "p"])
    rc = eai.cmd_cpa_upload(Sess(), args)
    assert rc == 1
    out = capsys.readouterr().out
    pipeline_calls = [p for p, _ in calls if p.endswith("/pipeline/run")]
    assert len(pipeline_calls) == 1  # 全局互斥触发只在末尾一次
    assert calls[-1][1] == {"mode": "table", "trigger": "manual"}  # 触发体契约
    assert "跳过 1" in out and "失败 1" in out and "上传 1" in out
    assert "解析管线已触发: run_id=run1" in out


def test_license_generate_output_guard(tmp_path, monkeypatch, capsys):
    """输出文件守卫：generate_license 静默不写文件（machine_id 缺失陷阱）→ rc=1 stderr；
    正常写文件 → rc=0 且参数逐项转发。"""

    def fake_lg(write):
        mod = types.ModuleType("license_generator")
        calls = []

        def generate_license(**kw):
            calls.append(kw)
            if write:
                Path(kw["output"]).write_text("LIC", encoding="utf-8")

        mod.generate_license = generate_license
        mod._calls = calls
        return mod

    req = tmp_path / "req.json"
    req.write_text('{"machine_id": "M1"}', encoding="utf-8")
    out = tmp_path / "out.lic"

    monkeypatch.setitem(sys.modules, "license_generator", fake_lg(write=False))
    rc = eai.main(["license", "generate", str(req), "--output", str(out)])
    assert rc == 1
    assert "未产生" in capsys.readouterr().err

    monkeypatch.setitem(sys.modules, "license_generator", fake_lg(write=True))
    rc = eai.main(["license", "generate", str(req), "--permanent", "--all-modules", "--customer", "测试客户", "--output", str(out)])
    assert rc == 0 and out.exists()
    forwarded = sys.modules["license_generator"]._calls[0]
    assert forwarded["permanent"] is True and forwarded["all_modules"] is True
    assert forwarded["customer"] == "测试客户" and forwarded["request_file"] == str(req)
