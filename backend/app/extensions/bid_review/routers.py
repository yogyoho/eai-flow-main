"""bid_review 工作台 API——Task 9 先空壳(仅 router,供 gateway 挂载;包 __init__ 自注册
五张表进 Base.metadata),Task 10 填充 8 端点(设计文档 §4.7)。"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/extensions/bid-review", tags=["Bid Review"])
