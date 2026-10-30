"use client";

/**
 * 基准确认页(bid:page:baseline)——Task 17 Step 2。
 * EAI-CUSTOM (2026-10-30): 参照 docs/designs/2026-10-30-bid-review-ui.html 原型 s4
 * (基准确认卡点)重整外观;类词汇表=app/bid-review/bid-review.css(.brx 作用域:
 * .screen/.proto-banner/.page-head/.f-card/.gate-bar/.meter/.note-bar/.pill-*)。
 * 行为契约不变:useBidTask 详情 + useBidConfirmTask 确认门;仅 awaiting_confirm 可确认
 * (gateOpen gating);409(ApiError.status)分流 toast「存在未复核致命项」照旧。
 *
 * landed 后端契约缺口(v1 已记,诚实降级,页内 note-bar 注明):
 * - 基线字段级快照无 HTTP 读端点(仅 MCP bid_review_baseline_get 可达)→ 原型 s4 的
 *   字段族列表/字段卡/冲突裁定交互无处落,本页以 engine_meta.docs 材料卡(f-card:
 *   doc_id/role pill/字符数可估——v1 上传时解码纯文本直存,text 随行)替代;
 * - 行级 confirmed 明细同缺口 → 进度按确认门状态位(awaiting_confirm=0%,过门=100%)。
 */

import Link from "next/link";
import { useEffect } from "react";
import { toast } from "sonner";

import { ApiError } from "@/extensions/bid-review/api";
import { taskStatusPill } from "@/extensions/bid-review/components/primitives";
import { useBidConfirmTask, useBidTask } from "@/extensions/bid-review/hooks";
import { type PillTone } from "@/extensions/contract-price/components/ui/bits";

interface DocMeta {
  doc_id?: string;
  role?: string;
  /** v1 上传时解码的纯文本直存(routers.create_task);字符数可估的来源。 */
  text?: string;
}

function roleLabel(role: string | undefined): string {
  if (role === "tender") return "招标";
  if (role === "bid") return "投标";
  return role ?? "未知";
}

/** role → 原型 pill 档(招标=主色/投标=橙警示/未知=灰)。 */
function rolePillClass(role: string | undefined): string {
  if (role === "tender") return "pill-main";
  if (role === "bid") return "pill-orange";
  return "pill-gray";
}

/** taskStatusPill 的 PillTone → 原型 .pill-* 档(info 无专属档,归主色)。 */
const STATUS_PILL_CLASS: Record<PillTone, string> = {
  primary: "pill-main",
  success: "pill-ok",
  warn: "pill-warn",
  error: "pill-err",
  gray: "pill-gray",
  info: "pill-main",
};

export function BaselineView({ taskId }: { taskId?: string | null }) {
  const taskQuery = useBidTask(taskId ?? null);
  const confirm = useBidConfirmTask();

  const task = taskQuery.data ?? null;
  const gateOpen = task?.status === "awaiting_confirm";
  // 材料行来自 engine_meta.docs(任务详情随带;逐行 payload 的字段快照无读端点)
  const docs = Array.isArray(task?.engine_meta?.docs)
    ? (task.engine_meta.docs as DocMeta[])
    : [];

  useEffect(() => {
    if (confirm.isError) {
      const err = confirm.error;
      // 确认门 409 → toast「存在未复核致命项」(spec §3.2/§3.3;Task 15 收紧落地即生效)
      toast.error(
        err instanceof ApiError && err.status === 409
          ? "存在未复核致命项"
          : (err?.message ?? "确认失败"),
      );
    }
  }, [confirm.isError, confirm.error]);

  if (!taskId) {
    return (
      <div className="screen on">
        <div className="page-head">
          <div className="ph-icon">
            <svg className="ic" viewBox="0 0 24 24" aria-hidden>
              <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
            </svg>
          </div>
          <div>
            <h2>基准确认</h2>
            <div className="ph-sub">
              逐条核对基准后再确认——基准错误将批量产生错误结论
            </div>
          </div>
        </div>
        <div className="note-bar warnbar">
          <svg
            className="ic"
            viewBox="0 0 24 24"
            aria-hidden
          >
            <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
            <path d="M12 9v4M12 17h.01" />
          </svg>
          <span>未指定任务——请从任务列表进入。</span>
        </div>
        <Link
          href="/bid-review"
          className="btn btn-sec"
          style={{ marginTop: 12 }}
        >
          返回任务列表
        </Link>
      </div>
    );
  }

  const st = task ? taskStatusPill(task.status) : null;
  // 进度按确认门状态位(行级 confirmed 明细无读端点,v1 已记缺口)
  const gatePct = gateOpen ? 0 : task ? 100 : 0;
  // materials_hash 安全取串(no-base-to-string):engine_meta 为 Record<unknown>
  const rawHash = task?.engine_meta?.materials_hash;
  const materialsHash = typeof rawHash === "string" ? rawHash : "";

  return (
    <div className="screen on">
      <div className="proto-banner">
        <b>P0-3</b>· 卡点页 · 引擎抽取 → 人工确认基准包 → 解锁审查 ·
        未确认不得进入审查(不可绕过)
      </div>

      <div className="page-head">
        <div className="ph-icon">
          <svg className="ic" viewBox="0 0 24 24" aria-hidden>
            <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
          </svg>
        </div>
        <div>
          <h2>招标基准确认</h2>
          <div className="ph-sub">
            任务 {taskId.slice(0, 8)} ·
            确认招标要求——未完成将不能开始审查 ·
            确认门仅工作台 UI,agent 不可代确认
          </div>
        </div>
        <div className="ph-actions">
          {st ? (
            <span className={`pill ${STATUS_PILL_CLASS[st.tone]}`}>
              {st.tone === "warn" ? (
                <span className="dot dot-warn" aria-hidden />
              ) : null}
              {st.label}
            </span>
          ) : null}
          <button
            type="button"
            className="btn btn-sec btn-sm"
            onClick={() => void taskQuery.refetch()}
            disabled={taskQuery.isFetching}
          >
            刷新
          </button>
        </div>
      </div>

      {/* 页顶警示(原型 s4 卡点语义):基准错误将批量产生错误结论 */}
      <div className="note-bar warnbar">
        <svg className="ic" viewBox="0 0 24 24" aria-hidden>
          <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
          <path d="M12 9v4M12 17h.01" />
        </svg>
        <span>基准错误将批量产生错误结论——逐条核对后再确认。</span>
      </div>

      {taskQuery.isError ? (
        <div className="note-bar errbar">
          <svg className="ic" viewBox="0 0 24 24" aria-hidden>
            <circle cx="12" cy="12" r="10" />
            <path d="M12 8v4M12 16h.01" />
          </svg>
          <span style={{ flex: 1 }}>
            任务加载失败:{taskQuery.error.message}
          </span>
          <button
            type="button"
            className="btn btn-sec btn-sm"
            onClick={() => void taskQuery.refetch()}
          >
            重试
          </button>
        </div>
      ) : null}

      {/* 材料卡(engine_meta.docs;字段级快照核对卡待读端点落地后接入,见下方 note-bar) */}
      <div style={{ marginTop: 12 }}>
        {taskQuery.isPending ? (
          <div className="f-card">
            <div className="f-hd">
              <span className="f-path">任务加载中…</span>
            </div>
            <div className="f-src">正在读取任务详情与基线材料。</div>
          </div>
        ) : docs.length === 0 ? (
          <div className="f-card">
            <div className="f-hd">
              <span className="f-path">该任务无基线材料</span>
            </div>
            <div className="f-src">任务未生成基线(检查上传材料或重新发起)。</div>
          </div>
        ) : (
          docs.map((d, idx) => {
            const chars = typeof d.text === "string" ? d.text.length : null;
            return (
              <div className="f-card" key={`${d.doc_id ?? "doc"}-${idx}`}>
                <div className="f-hd">
                  <span className="f-path" title={d.doc_id}>
                    {d.doc_id ?? "—"}
                  </span>
                  <span className={`pill ${rolePillClass(d.role)}`}>
                    {roleLabel(d.role)}
                  </span>
                  <span
                    className={`pill ${gateOpen ? "pill-warn" : "pill-ok"}`}
                    style={{ marginLeft: "auto" }}
                  >
                    {gateOpen ? "待确认" : "已过确认门"}
                  </span>
                </div>
                <div className="f-val">
                  <span className="num">
                    {chars === null ? "—" : chars.toLocaleString()}
                  </span>{" "}
                  字符
                  <span
                    style={{
                      fontWeight: 400,
                      fontSize: 12,
                      color: "var(--text-3)",
                    }}
                  >
                    (按文档内联文本估算)
                  </span>
                </div>
                <div className="f-src">
                  来源 上传文件纯文本 · 基线快照哈希{" "}
                  <code className="k">
                    {materialsHash.slice(0, 12) || "—"}
                  </code>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* 诚实降级注记(landed 契约缺口,勿粉饰) */}
      <div className="note-bar">
        <svg className="ic" viewBox="0 0 24 24" aria-hidden>
          <circle cx="12" cy="12" r="10" />
          <path d="M12 16v-4M12 8h.01" />
        </svg>
        <span>
          基线字段级快照暂无 REST
          读端点(仅 MCP 可达),字段级抽取与冲突裁定由引擎完成;本页人工门=确认基准包后审查继续。
        </span>
      </div>

      {/* 确认门置底(gate-bar,原型 s4);点击触发后端 409 收紧逻辑 */}
      <div className="gate-bar">
        <div style={{ flex: 1, minWidth: 200 }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>
            基准确认进度{" "}
            <span className="num">
              {gateOpen
                ? "0%(待确认)"
                : task
                  ? "100%(已过确认门)"
                  : "—"}
            </span>
          </div>
          <div className="g-info">
            {gateOpen
              ? "卡点:基准确认前任务停留在待确认状态,不进入审查;确认后任务续跑(running→审查完成)。"
              : task
                ? "任务已过确认门,审查继续;改错可回到本页重新确认。"
                : "当前状态无待确认基线(仅 awaiting_confirm 状态可确认)。"}
          </div>
        </div>
        <span className="meter" style={{ width: 120 }}>
          <i style={{ width: `${gatePct}%` }} />
        </span>
        <button
          type="button"
          className="btn btn-pri"
          disabled={!gateOpen || confirm.isPending}
          onClick={() =>
            confirm.mutate(taskId, {
              onSuccess: () => toast.success("基线已确认,审查续跑中"),
            })
          }
        >
          {confirm.isPending ? "确认中…" : "确认基准包并开始审查"}
        </button>
      </div>
    </div>
  );
}
