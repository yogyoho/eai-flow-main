#!/usr/bin/env python3
"""eai.py — 系统统一模块运维 CLI（薄 REST 客户端，spec 2026-09-03）。

两类子命令：服务端型（gsb/cpa，需登录会话）与本地工具型（license，免会话）。
依赖：stdlib + httpx（禁止 import app.*/deerflow.*——部署域隔离，可独立拷贝到运维机执行）。
凭据不落盘（HTTP 会话 cookie 进程内有效，批量任务须单进程内完成，中断重跑即重登录）；
注意 --password 会进 shell history，推荐改用 EAI_PASSWORD 环境变量免密传参。

EAI-CUSTOM (geo-batch-cli, spec 2026-09-03): 新增独立运维工具。

契约锚点（recon 实证，勿凭印象改动）：
- 登录 POST /api/extensions/auth/login，body {"username","password"}（工号/邮箱二合一）；
  httpx 默认不带 Origin 头——勿手工添加（带即 403 Cross-site auth request denied）；
  成功响应 token 只在 Set-Cookie（access_token HttpOnly + 中间件补种 csrf_token），不在响应体。
- 登录限流桶 5 次/5 分钟 IP 共享（nginx:2026 整入口共享，含真人）→ 429 必须 raise
  LoginLocked 并绝不自动重试。
- CSRF 双提交：cookie csrf_token 原样回填 X-CSRF-Token（token_urlsafe 本身 URL 安全，勿二次解码）；
  仅状态变更方法（POST/PUT/DELETE/PATCH）需要。
- 探活 GET /api/v1/auth/me：200=有效 / 401=失效（勿用 /api/permissions/me——无权限用户 403 误判）。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx

SESSION_FILE = Path.home() / ".eai" / "session.json"  # T6 断点 state 预留位
LOGIN_PATH = "/api/extensions/auth/login"
PROBE_PATH = "/api/v1/auth/me"
CSRF_HEADER = "X-CSRF-Token"


class LoginLocked(Exception):
    """登录限流（429，5 次/5 分钟 IP 共享桶）——调用方必须停止重试。"""


class Session:
    """登录后的 REST 会话：cookie jar 持 access_token，post/delete 自动拼 CSRF 双提交头。"""

    def __init__(self, base_url: str, client: httpx.Client, csrf: str):
        self.base_url = base_url.rstrip("/")
        self.client = client
        self.csrf = csrf or ""

    def _url(self, path: str) -> str:
        """相对路径拼 base_url；绝对 URL（http/https 开头）原样透传——httpx 按 host 匹配 cookie jar。"""
        if path.startswith(("http://", "https://")):
            return path
        return self.base_url + path

    def headers(self) -> dict:
        return {CSRF_HEADER: self.csrf}

    def get(self, path: str, **kw):
        return self.client.get(self._url(path), **kw)

    def post(self, path: str, **kw):
        headers = dict(kw.pop("headers", None) or {})
        if self.csrf:
            headers.update(self.headers())  # CSRF 双提交：状态变更方法必带（无 csrf 则不发空头）
        return self.client.post(self._url(path), headers=headers, **kw)

    def delete(self, path: str, **kw):
        headers = dict(kw.pop("headers", None) or {})
        if self.csrf:
            headers.update(self.headers())
        return self.client.delete(self._url(path), headers=headers, **kw)


def login(base_url: str, username: str, password: str, transport: httpx.BaseTransport | None = None) -> Session:
    """登录并返回 Session；429 → LoginLocked（绝不自动重试——限流桶 IP 共享会把入口锁满 5 分钟）。"""
    client = httpx.Client(base_url=base_url, timeout=120.0, transport=transport)
    resp = client.post(LOGIN_PATH, json={"username": username, "password": password})
    if resp.status_code == 429:
        client.close()
        raise LoginLocked("5 次/5 分钟 IP 共享桶已满——稍后再试，请勿连续重试")
    resp.raise_for_status()
    # Set-Cookie 已自动入 jar；response.cookies 与 client.cookies 双路取值（后者为 httpx 实测兜底）
    csrf = resp.cookies.get("csrf_token") or client.cookies.get("csrf_token")
    return Session(base_url, client, csrf or "")


def probe(sess: Session, transport: httpx.BaseTransport | None = None) -> bool:
    """探活 /api/v1/auth/me：200=有效 / 401=失效。transport 参数为签名统一占位（client 已持）。"""
    return sess.get(PROBE_PATH).status_code == 200


SUBCOMMANDS: dict[str, dict] = {}  # name -> {"help":…, "needs_session": bool, "func": callable}


def register(name: str, help_text: str, needs_session: bool = True):
    """子命令注册表装饰器：needs_session 命令自动获得 --username/--password 并在 main 内登录探活。"""

    def deco(fn):
        SUBCOMMANDS[name] = {"help": help_text, "needs_session": needs_session, "func": fn}
        return fn

    return deco


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="eai.py", description="EAI 系统统一模块运维 CLI")
    ap.add_argument("--base-url", default="http://localhost:2026")
    sub = ap.add_subparsers(dest="command", required=True)
    for name, meta in SUBCOMMANDS.items():
        sp = sub.add_parser(name, help=meta["help"])
        if meta["needs_session"]:
            sp.add_argument("--username", required=True, help="工号或邮箱")
            # 密码优先 EAI_PASSWORD env（--password 会进 shell history）；env 未设时才强制 --password。
            # 勿写 required=True + default：argparse 对 required 参数无视 default，env 回退会彻底失效。
            sp.add_argument(
                "--password",
                default=os.environ.get("EAI_PASSWORD"),
                required="EAI_PASSWORD" not in os.environ,
                help="密码（仅进程内会话；推荐 EAI_PASSWORD env 免进 shell history）",
            )
        if hasattr(meta["func"], "register_args"):  # T6 子命令自定义参数入口
            meta["func"].register_args(sp)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    meta = SUBCOMMANDS[args.command]
    if meta["needs_session"]:
        # 顶层错误面：限流/认证失败人话报错，不裸 traceback。try 只罩登录+探活——
        # 子命令自身的 HTTPStatusError（如 409）不得误报成「登录失败」。
        try:
            sess = login(args.base_url, args.username, args.password)
            if not probe(sess):
                print("会话探活失败", file=sys.stderr)
                return 2
        except LoginLocked as e:
            print(f"登录限流: {e}", file=sys.stderr)
            return 3
        except httpx.HTTPStatusError as e:
            print(f"登录失败: {e.response.status_code}（检查工号/密码）", file=sys.stderr)
            return 3
        return meta["func"](sess, args)
    return meta["func"](args)


if __name__ == "__main__":
    sys.exit(main())
