-- 一次性迁移：把 app_definitions.license_module 对齐 v2 五键方案 (platform + 4 商业键)。
-- 在每个已存在的部署上、签发首张正式 license 之前跑一次。幂等。
-- 新部署靠 database.py 种子自动得到正确值，无需跑此脚本。
--
-- 运行方式（扩展库 postgres 容器内）：
--   docker exec -i eai-docker-postgres-ext-1 psql -U agentflow -d agentflow < scripts/migrate_license_modules_v2.sql
-- 先确认容器名：docker compose -p eai-docker ps

BEGIN;

-- 基础平台模块 (7 个基础模块 → platform)
UPDATE app_definitions SET license_module = 'platform'      WHERE app_id IN ('smart-writing', 'docmgr', 'knowledge-factory', 'knowledge', 'admin');
-- 商业模块
UPDATE app_definitions SET license_module = 'dashboard'      WHERE app_id = 'dashboard';
UPDATE app_definitions SET license_module = NULL             WHERE app_id IN ('docmgr', 'knowledge', 'knowledge-factory');
UPDATE app_definitions SET license_module = 'typography'     WHERE app_id = 'output';
UPDATE app_definitions SET license_module = 'contract_price' WHERE app_id = 'procurement';
UPDATE app_definitions SET license_module = 'contract_price' WHERE app_id = 'contract-price-analysis';
UPDATE app_definitions SET license_module = 'project'        WHERE app_id = 'workflow-admin';

COMMIT;

-- 验证：非空 license_module 应只含 4 个键
-- SELECT app_id, license_module FROM app_definitions WHERE license_module IS NOT NULL ORDER BY app_id;
