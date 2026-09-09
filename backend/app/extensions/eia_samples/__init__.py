# EAI-CUSTOM: 煤矿环评报告样例库——独立扩展模块（原为 knowledge_factory 内的样例库 tab，
# 2026-09 迁出：KF 是通用模块，领域样例库不得混入；端点行为不变，仅换归属）。
"""Coal EIA report sample bank extension (表 kf_samples，沿用历史表名免数据迁移).

样例 = 已解析环评报告文件的登记记录。台账双轴：scenario（场景）× status（解析状态）；
file_hash 全局唯一，import-bulk 按哈希 upsert 幂等。

表创建机制：本包导入即把 KFSample 模型注册到共享 ``app.extensions.database`` Base，
gateway 启动序 init_db（create_all）→ migrate_db 保证建表（同 geo_samples 机制）；
历史表名 ``kf_samples`` 与类名原样沿用（dev/生产库已存在，无需迁移；原 database.py
migrate_db 内的 kf_samples 建表 SQL 块由此机制取代）。

管理路由挂载于 Gateway ``/api/extensions/eia-samples``（routers.py）；
种子台账 data/kf_samples_seed.json 由 backend/scripts/eia_seed_samples.py 灌入。
"""

from app.extensions.eia_samples.models import KFSample  # noqa: F401
from app.extensions.eia_samples.routers import router  # noqa: F401

__all__ = ["router", "KFSample"]
