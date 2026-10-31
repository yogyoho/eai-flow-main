"use client";

/**
 * 六步步骤条(原型 s3)+ 引擎进度行。
 * EAI-CUSTOM (2026-10-31 UX 重构 Plan6,spec §4.3):canonical home=/parsing 归拢
 * 专屏;自 WorkbenchView 上移为共享件——workbench 在 M3 /results 拆分前暂留显示
 * (共享组件,非重复实现),届时拆分即随区段一移除。
 */
import { cn } from "@/lib/utils";

import { type TaskOut } from "@/extensions/bid-review/types";

// ── 步骤条(原型 s3:6 步;stage 词汇=worker progress.stage)──────────────
const STAGE_LABELS = [
  "已创建",
  "文档解析",
  "字段抽取",
  "基准确认",
  "审查执行",
  "完成",
] as const;

const STAGE_INDEX: Record<string, number> = {
  created: 0,
  parsing: 1,
  extracting: 2,
  confirm_gate: 3,
  review: 4,
  done: 5,
};

/** 当前步:progress.stage 优先;缺失时按任务状态兜底(测试夹具/早期任务无 stage)。 */
export function resolveStageIdx(stageRaw: string | null, status: string): number {
  if (stageRaw && stageRaw in STAGE_INDEX) return STAGE_INDEX[stageRaw]!;
  switch (status) {
    case "done":
    case "completed":
      return 5;
    case "running":
      return 4;
    case "awaiting_confirm":
      return 3;
    case "extracting":
      return 2;
    case "parsing":
      return 1;
    default:
      return 0;
  }
}

export function TaskStepper({ task }: { task: TaskOut | null }) {
  // 步骤条输入:task.progress {stage,pct,msg} → done/on
  const progress: Record<string, unknown> = task?.progress ?? {};
  const stageRaw = typeof progress.stage === "string" ? progress.stage : null;
  const pctVal = typeof progress.pct === "number" ? progress.pct : null;
  const progressMsg = typeof progress.msg === "string" ? progress.msg : "";
  const stageIdx = resolveStageIdx(stageRaw, task?.status ?? "");
  const taskDone = task?.status === "done";
  return (
    <>
      <div className="stepper">
        {STAGE_LABELS.map((label, i) => (
          <span
            key={label}
            className={cn(
              "step",
              (taskDone || i < stageIdx) && "done",
              !taskDone && i === stageIdx && "on",
            )}
          >
            <span className="sn">{i + 1}</span>
            {label}
          </span>
        ))}
      </div>
      {progressMsg ? (
        <div className="tbl-foot">
          引擎:{progressMsg}
          {pctVal != null ? <span className="num"> · {pctVal}%</span> : null}
        </div>
      ) : null}
    </>
  );
}
