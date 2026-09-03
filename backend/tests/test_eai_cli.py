"""统一 CLI（tools/eai.py）单元测试——importlib 加载，httpx.MockTransport 假网络。"""

import importlib.util
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
