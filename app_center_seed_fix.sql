-- app_center_seed_fix.sql — manually seed the 5 domains + 10 built-in apps
-- (workaround for the gateway-seed bug where raw-SQL INSERT omitted `id` → NotNullViolation).
-- Idempotent (ON CONFLICT DO NOTHING). Run via: psql -U agentflow -d agentflow -f this.sql

-- Domains
INSERT INTO app_domains (key, label, accent_color, sort_order, is_universal) VALUES
  ('universal',    '通用工具', 'blue',   0, TRUE),
  ('admin',        '系统管理', 'slate',  1, TRUE),
  ('report',       '报告编撰', 'violet', 2, FALSE),
  ('knowledge',    '知识管理', 'cyan',   3, FALSE),
  ('procurement',  '采购管理', 'amber',  4, FALSE)
ON CONFLICT DO NOTHING;

-- Apps (id via gen_random_uuid() — the missing piece)
INSERT INTO app_definitions
  (id, app_id, name, description, icon_name, business_domain, stage_tag,
   path, license_module, admin_only, sort_order, sort_key, is_builtin)
VALUES
  (gen_random_uuid(), 'dashboard',         '工作台',     '待办聚合与项目进度概览，开启高效的一天',           'layout-dashboard', 'universal',   'overview',    '/dashboard',         'dashboard',      FALSE, 1,  'gongzuotai',    TRUE),
  (gen_random_uuid(), 'smart-writing',     '智能写作',   'AI 辅助写作，从提纲到终稿全流程智能生成',         'bot',              'universal',   'process',     '/writing',           'platform',       FALSE, 2,  'zhinengxiezuo', TRUE),
  (gen_random_uuid(), 'projects',          '报告项目',   '管理报告项目全生命周期，章节分配与审批跟踪',       'clipboard-list',   'report',      'collaborate', '/projects',          'project',        FALSE, 3,  'baogaoxiangmu', TRUE),
  (gen_random_uuid(), 'docmgr',            '文档空间',   '团队文档协作中心，多人实时编辑与版本管理',         'folder-check',     'universal',   'collaborate', '/docmgr',            'platform',       FALSE, 4,  'wendangkongjian', TRUE),
  (gen_random_uuid(), 'knowledge-factory', '知识工厂',   '结构化知识生产流水线，从原始资料到可用知识库',     'factory',          'knowledge',   'process',     '/knowledge-factory', 'platform',       FALSE, 5,  'zhishigongchang', TRUE),
  (gen_random_uuid(), 'knowledge',         '知识库',     '检索企业知识资产，RAG 增强问答与智能引用',         'book-open',        'knowledge',   'retrieve',    '/knowledge',         'platform',       FALSE, 6,  'zhishiku',      TRUE),
  (gen_random_uuid(), 'output',            '报告输出',   '一键生成多格式报告成果，模板化排版与导出',         'file-output',      'report',      'output',      '/output',            'typography',     FALSE, 7,  'baogaochushu',  TRUE),
  (gen_random_uuid(), 'procurement',       '采购管理',   '合同价格分析与采购分项管理，聚类归并与统计',       'package-search',   'procurement', 'process',     '/contract-price',    'contract_price', FALSE, 8,  'caigouguanli',  TRUE),
  (gen_random_uuid(), 'admin',             '系统管理',   '用户、角色、部门与权限的统一管理后台',             'settings-2',       'admin',       'manage',      '/admin',             'platform',       TRUE,  9,  'xitongguanli',  TRUE),
  (gen_random_uuid(), 'workflow-admin',    '流程管理',   '审批流程模板的设计、编辑与版本管理',               'file-text',        'universal',   'manage',      '/workflow-admin',    'project',        TRUE,  10, 'liuchengguanli', TRUE)
ON CONFLICT (app_id) DO NOTHING;

-- Verify
SELECT 'domains' AS t, COUNT(*) FROM app_domains
UNION ALL
SELECT 'apps', COUNT(*) FROM app_definitions;
