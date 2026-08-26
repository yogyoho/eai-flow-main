// frontend/src/extensions/license/labels.ts
/**
 * Canonical license module key → user-facing label.
 *
 * Single source shared by ModuleLockedPage (lock screen) and the admin
 * App Management dropdown. Keys MUST stay in sync with backend
 * app.extensions.license.service.ALL_MODULES — guarded by
 * backend/tests/test_license_modules_sync.py.
 */
export const MODULE_LABELS: Record<string, string> = {
  platform: "基础平台",
  project: "项目协作",
  dashboard: "工作台",
  typography: "报告输出",
  contract_price: "合同价格分析",
  spare_parts: "备品备件价格分析",
  bid_quote: "投标报价分析",
  biz_pipeline: "市场经营分析",
  sales_personnel: "销售人员",
};
