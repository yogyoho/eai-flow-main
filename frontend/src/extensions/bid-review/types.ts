/**
 * TypeScript types for the bid-review extension API.
 *
 * Field names mirror the backend Pydantic schemas (snake_case) exactly —
 * `backend/app/extensions/bid_review/schemas.py`(Task 2;A8:verdict/action
 * 均为引擎产出层取值,false_positive 等人工回写值仅落库不经 schema 校验)。
 */

/** 审查任务(backend TaskOut)。status 词汇=后端 models.py:30:created|parsing|extracting|
 * awaiting_confirm|running|done|failed(终态成功=done,后端无 completed;Task 12 修复轮勘误);
 * mode: quick|deep */
export interface TaskOut {
  id: string;
  owner_id: string;
  status: string;
  mode: string;
  progress: Record<string, unknown>;
  error: string | null;
  engine_meta: Record<string, unknown>;
  prev_task_id: string | null;
  created_at: string;
  /** 每任务问题计数(micro-A 2026-10-29):仅 GET /tasks 列表聚合填充;单任务端点
   * null=未统计(禁伪零)。fatal_unhandled=fatal 且未被人工判误报(verdict≠
   * false_positive,误报回流后自然回落);need_human_count=need_human 旗标计数。 */
  fatal_unhandled: number | null;
  need_human_count: number | null;
  /** ── B1 扩展(EAI-CUSTOM 2026-10-31,spec §5 B1/裁定12)──────────
   * biz_no=业务号 TBR-YYYYMMDD-NNNN(存量迁移回填);项目/标段/编号=抽取回填
   * (老任务 null,须重跑抽取才有);updated_at=行级更新时刻;done_at=完成时刻
   * (set_status 一次性落点,存量不伪造)。main_unhandled/created_by_name 仅
   * GET /tasks 列表聚合填充,单任务端点 null=未统计(伪零纪律)。TS 侧可选:
   * 后端恒输出,镜像可选只为容忍旧测试夹具。 */
  biz_no?: string | null;
  project_name?: string | null;
  lot_name?: string | null;
  tender_no?: string | null;
  updated_at?: string | null;
  done_at?: string | null;
  main_unhandled?: number | null;
  created_by_name?: string | null;
}

/** 审查问题(backend IssueOut)。 */
export interface IssueOut {
  id: string;
  task_id: string;
  rule_id: string;
  layer: string;
  severity: string;
  /** 引擎五值 FAIL|PASS|UNKNOWN|ERROR|SKIP(后端 P1-β批三 C-08)+ 复核域 false_positive。 */
  verdict: string;
  clause_id: string | null;
  message: string;
  fix: string;
  evidence: unknown[];
  dedup_key: string;
  need_human: boolean;
  confidence: number;
  /** B2 复核投影(unresolved|maintained|false_positive|severity_changed|deferred);旧网关缺省。 */
  review_state?: string;
  /** EAI-CUSTOM(L2 P2):实体键(落库)/跨层去重投影(grouped_into+related,现算);旧网关缺省。 */
  entity_keys?: string[];
  grouped_into?: string | null;
  related_issues?: Array<{
    id: string;
    rule_id: string;
    layer: string;
    severity: string;
    message: string;
  }>;
  created_at: string;
}

/** 基准包(backend BaselineOut)。 */
export interface BaselineOut {
  id: string;
  task_id: string;
  kind: string;
  payload: Record<string, unknown>;
  confirmed: boolean;
  created_at: string;
}

/** 审查汇总(backend worker.summarize_issues;worker 落 progress.summary 与 issues
 * 列表 API summary 共用本实现,两侧口径一致)。fatal/major/minor/info 仅计
 * need_human=False 的正式违规(排 layer=="L4",advisory 单列);need_human 单列待人工
 * 计数。rules_total/unknown_ratio/advisory 为逐批 additive 键(旧网关缺省 → 消费方
 * `??` 兜底)。前端 ResultsView 现于客户端复算可见口径(summary 字段在前端 api 层
 * 不可达),本接口为后端全量口径的契约锚(TaskOut.progress 以 Record 透传)。
 */
export interface Summary {
  fatal: number;
  major: number;
  minor: number;
  info: number;
  need_human: number;
  rules_total?: number | null;
  unknown_ratio?: number | null;
  advisory?: { total: number; by_severity: Record<string, number> };
  /** 批五(A-β5-⑥),规格 §5.7.2 四态派生键(worker.compute_gate_status;
   * SUBMITTABLE|CONDITIONAL|NOT_SUBMITTABLE|PENDING_HUMAN)。旧 summary 无此键。 */
  gate_status?: string;
}
