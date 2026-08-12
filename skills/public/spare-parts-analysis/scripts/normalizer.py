# EAI-CUSTOM: NEW(④ 独有)——客户脏键归一层(D3)。
"""Customer dirty-key normalization (D3 混合归一:客户走主数据/别名表)。

OCR 抽出的 customer_name 是脏的(同一客户有多种写法:"桂北矿业"/"桂北矿业集团"/
"桂北矿业股份有限公司")。本层把脏名归一到 customer_id:

  - 命中:canonical_name 完全相等,或在 aliases 列表里 → 复用既有客户,返回其 id。
  - 未命中:绝不静默丢——新建一条 status=pending 的 csp_customers(canonical_name=脏名,
    source=ocr),返回其 id。管理前端(T7 认领 UI)再把 pending 客户合并/认领到规范客户。

备件名归一走另一条路——聚类引擎(clustering/engine),不在本层。cluster_id 是跨客户
比价键;csp_items.customer_id 是分组维度。两者正交。
"""

import logging
import uuid

logger = logging.getLogger(__name__)


async def resolve_customer(session, customer_name: str | None) -> tuple:
    """把脏 customer_name 归一到 (customer_id, canonical_name, created_pending)。

    在调用方已开的 session 内操作(命中复用 / 未命中新增 pending 客户),调用方负责 commit。
    返回 (uuid|None, str|None, bool):created_pending=True 表示本次新建了一条待认领客户。

    ponytail: 全量扫描 csp_customers 做内存匹配——客户数 N 极小(数十量级),远低于
    值得为它加 GIN/JSONB 索引的阈值。若客户表涨到万级再换 JSONB 包含查询。
    """
    if not customer_name:
        return None, None, False
    from sqlalchemy import select

    from scripts.models import CspCustomer

    name = customer_name.strip()
    rows = (await session.execute(select(CspCustomer))).scalars().all()
    for c in rows:
        if c.canonical_name == name:
            return c.id, c.canonical_name, False
        if name in (c.aliases or []):
            return c.id, c.canonical_name, False
    # 未命中 → 新建 pending 客户(永不静默丢)
    cust = CspCustomer(canonical_name=name, aliases=[], source="ocr", status="pending")
    session.add(cust)
    await session.flush()
    logger.info("新建待认领客户: %s (id=%s)", name, cust.id)
    return cust.id, name, True


def is_valid_uuid(v) -> bool:
    """防御:判断字符串/uuid 是否合法 UUID(认领/合并接口的入参校验用)。"""
    try:
        if isinstance(v, uuid.UUID):
            return True
        uuid.UUID(str(v))
        return True
    except (ValueError, AttributeError, TypeError):
        return False
