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
    # 状态变更请求自动带 X-CSRF-Token
    sess.post("http://x/api/extensions/geo-samples/documents/d1/parse", transport=transport)
    m, p, h = calls[-1]
    assert h["X-CSRF-Token"] == "tok456"


def test_login_429_respects_lockout():
    def handler(request):
        return httpx.Response(429, json={"detail": "Too many login attempts. Try again later."})

    with pytest.raises(eai.LoginLocked):
        eai.login("http://x", "u", "p", transport=httpx.MockTransport(handler))
