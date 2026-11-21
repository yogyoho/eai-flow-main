/**
 * bid-write 用户可见文案中心（UX 评审 P0）。
 *
 * 原则：界面不出现开发批次号、内核字段名、断言编号等术语；文案改这里，组件只引用。
 * 与后端枚举相关的展示值词表仍在 helpers.ts，本文件只放页面级长文案与行为说明。
 */

export const GENERATE_COPY = {
  subtitle: "录入质保、报价等商务参数，据此生成投标正文",
  subtitleNoTask: "先录入关键商务参数，系统据此生成并校验正文",
  boqEmptyTitle: "本次招标未提取到工程量清单",
  boqEmptyHint: "无需逐项报价。可直接使用下方参数区填写质保期等商务承诺。",
  FIELD_TARGETS: {
    warranty_period: "将写入：投标函质保条款、技术方案质保承诺",
    general_commitments: "将写入：承诺条款清单",
    unit_prices: "将写入：报价一览表单价列",
    sign_date: "将写入：投标函落款日期",
    price_note: "将写入：报价说明栏",
  },
  paramsTitle: "商务参数",
  paramsBadge: "未填写的参数保持默认",
  runHint: "点击「开始生成」后：套用上方参数生成正文，并自动执行质量检查",
} as const;

export const WORKBENCH_COPY = {
  subtitle: "编辑投标正文、补全占位符、发起审批",
  quickGuide:
    "点击正文中的黄色高亮即可填写；表格可用工具条「＋行/－行」增删行；蓝框为招标格式锁定区，不可改写。",
  submitChecks: (d0: number, d1: number, d2: number) =>
    `提交检查：${d0} 项必须通过 · ${d1} 项建议 · ${d2} 项提示`,
  coverage: (count: number, rate: string) =>
    `质量检查覆盖 ${count} 项 · 通过率 ${rate}`,
  unnamedPlaceholder: "未命名占位符",
} as const;

export const REVIEW_COPY = {
  blockedHint:
    "最近一次检查存在会阻止导出的问题。先处理下方待补清单，再回③重新生成以刷新检查结果。",
  bottomNote: "仅展示需要处理或跳过的检查项；通过项不再重复列出。",
  snapshotBadge: "结果为最近一次生成时的检查快照",
} as const;

export const EXPORT_COPY = {
  subtitle: "交付前检查与文件导出",
  revisionStateLabels: {
    submitted: "已提交审批",
    approved: "已批准",
    rejected: "已退回",
    draft: "草稿",
  } as Record<string, string>,
} as const;

export const LIBRARY_COPY = {
  subtitle:
    "资质 / 业绩 / 人员 / 产能 / 网点 / 历史标书 · 全项目共用，供各写作任务引用佐证",
  empty: "从「新建实体」补录资质、业绩等六类素材；被写作任务引用的素材才算有效佐证。",
  emptyFiltered: "调整类型、佐证过滤或搜索词后再试。",
  footerNote:
    "导出前系统会检查素材是否被引用；补录引用后自动通过，无需手动标记。",
} as const;

export const PROJECTS_COPY = {
  untitledProject: "（项目名称编码异常）",
  flowIntro:
    "投标商务写作分六步：①解析确认 → ②素材核对 → ③生成配置 → ④写作工作台 → ⑤预审查 → ⑥导出适配。每一步完成后进入下一步；治理区的素材库与质量规则随时可用。",
  intakeNote:
    "上传招标文件后，系统自动解析并生成商务响应矩阵；解析失败会保留原因并支持重试。",
} as const;

export const MATERIALS_COPY = {
  subtitle: "写之前先看清缺口：未核对 / 已确认 / 无素材三态清单",
  statusHint: "矩阵状态 = 人工确认结果；素材状态 = 系统实时匹配结果",
} as const;

export const REGISTRY_COPY = {
  title: "质量规则中心",
  subtitle: "全部质量检查规则一览（只读）",
} as const;

/** 等级行为表的「渲染/预审状态/重试」常量 → 业务词（未知值原样展示，不猜测）。 */
export const ASSERTION_RENDER_LABELS: Record<string, string> = {
  TODO_BLOCK: "标红并列入待补清单",
  MARK_YELLOW: "标黄提醒",
  BOARD_ONLY: "仅面板展示",
  NONE: "不显示",
};

export const ASSERTION_PRE_LABELS: Record<string, string> = {
  MISSING: "显示缺失",
  UNKNOWN: "显示未知",
};

export const ASSERTION_RETRY_LABELS: Record<string, string> = {
  self_refine_max_2: "自动重试最多 2 次",
  self_refine_max_1: "自动重试最多 1 次",
  none: "不重试",
};
