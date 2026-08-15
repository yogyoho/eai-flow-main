"""OTP 登录核心 —— 生成、存储（bcrypt）、校验并通过企业 SMTP 发送一次性验证码。

EAI-CUSTOM 认证门面：纯 EAI 自有代码；复用 app.extensions.auth.jwt 的哈希/校验。
"""

import logging
import secrets
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.jwt import hash_password, verify_password
from app.extensions.config import get_extensions_config
from app.extensions.models import OtpCode

logger = logging.getLogger(__name__)


def generate_code(length: int = 6) -> str:
    """生成加密随机数字验证码."""
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


def code_is_valid(row: OtpCode | None, code: str, now: datetime) -> bool:
    """纯函数校验：记录存在、未过期、验证码哈希匹配."""
    if row is None:
        return False
    if row.expires_at < now:
        return False
    return verify_password(code, row.code_hash)


async def send_otp_email(email: str, code: str) -> str | None:
    """通过企业 SMTP 发送验证码.

    当 SMTP 未启用时返回验证码本身（dev/占位回显）——生产必须设 EAI_SMTP_ENABLED=true。
    邮件发送成功时返回 None。
    """
    cfg = get_extensions_config().smtp
    if not cfg.usable:
        logger.warning("SMTP disabled; OTP for %s would have been sent (dev echo)", email)
        return code

    msg = EmailMessage()
    msg["Subject"] = "登录验证码"
    msg["From"] = cfg.from_addr
    msg["To"] = email
    msg.set_content(f"您的登录验证码是：{code}，{get_extensions_config().otp.ttl_seconds // 60} 分钟内有效。")

    if cfg.use_tls:
        with smtplib.SMTP_SSL(cfg.host, cfg.port) as s:
            if cfg.user:
                s.login(cfg.user, cfg.password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(cfg.host, cfg.port) as s:
            s.starttls()
            if cfg.user:
                s.login(cfg.user, cfg.password)
            s.send_message(msg)
    return None


async def create_otp(db: AsyncSession, email: str) -> str | None:
    """生成、存储（bcrypt 哈希）、并发送验证码；返回 dev 回显码或 None."""
    cfg = get_extensions_config().otp
    code = generate_code(cfg.length)
    expires_at = datetime.now(UTC) + timedelta(seconds=cfg.ttl_seconds)
    db.add(OtpCode(email=email, code_hash=hash_password(code), expires_at=expires_at))
    await db.commit()
    return await send_otp_email(email, code)


async def verify_otp(db: AsyncSession, email: str, code: str) -> bool:
    """校验 email 最新的一条未用且未过期的验证码；成功则标记已用."""
    stmt = select(OtpCode).where(OtpCode.email == email, OtpCode.used_at.is_(None)).order_by(OtpCode.created_at.desc()).limit(1)
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    if not code_is_valid(row, code, datetime.now(UTC)):
        return False
    row.used_at = datetime.now(UTC)
    await db.commit()
    return True
