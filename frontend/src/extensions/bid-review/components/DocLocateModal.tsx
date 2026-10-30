"use client";

/**
 * 定位原文 modal(EAI-CUSTOM 2026-10-30,spec D6/D8)——自 WorkbenchView 抽出共享
 * (2026-10-30 分期建议一期 s4:BaselineView 字段卡「查看原文」同用)。
 * 证据 chip 点击 → 取命中页(pdf 真页码)或 quote ±10 段窗口(docx 无页码诚实降级);
 * 404「未定位到原文」如实呈现,不造假原文。
 */

import { AlertTriangle } from "lucide-react";
import { useEffect, useState } from "react";

import {
  type BidDocContent,
  type LocateTarget,
  ApiError,
  docAssetUrl,
  fetchDocContent,
} from "@/extensions/bid-review/api";
import { cn } from "@/lib/utils";

export function DocLocateModal({
  taskId,
  target,
  onClose,
}: {
  taskId: string;
  target: LocateTarget;
  onClose: () => void;
}) {
  const [state, setState] = useState<
    | { s: "loading" }
    | { s: "miss" }
    | { s: "err"; msg: string }
    | { s: "ok"; data: BidDocContent }
  >({ s: "loading" });

  useEffect(() => {
    let alive = true;
    setState({ s: "loading" });
    fetchDocContent(taskId, target.docId, {
      quote: target.page == null && target.quote ? target.quote : undefined,
      page: target.page ?? undefined,
    })
      .then((data: BidDocContent) => {
        if (alive) setState({ s: "ok", data });
      })
      .catch((e: unknown) => {
        if (!alive) return;
        if (e instanceof ApiError && e.status === 404) setState({ s: "miss" });
        else
          setState({
            s: "err",
            msg: e instanceof Error ? e.message : "原文取数失败",
          });
      });
    return () => {
      alive = false;
    };
  }, [taskId, target]);

  // 命中高亮:空白折叠后子串匹配(与后端定位口径一致)
  const quoteKey = target.quote ? target.quote.replace(/\s+/g, "") : "";

  return (
    <div
      className="overlay open"
      role="dialog"
      aria-modal="true"
      aria-label="定位原文"
    >
      <div className="modal" style={{ width: 720, maxWidth: "92vw" }}>
        <div className="modal-hd">
          <h3>
            定位原文 · {target.docId}
            {target.page != null ? (
              <span className="pill pill-gray" style={{ marginLeft: 8 }}>
                p.{target.page}
              </span>
            ) : null}
          </h3>
          <button
            type="button"
            className="x"
            aria-label="关闭"
            onClick={onClose}
          >
            ✕
          </button>
        </div>
        <div className="modal-bd">
          {state.s === "loading" ? (
            <p style={{ color: "var(--text-3)", fontSize: 13 }}>原文加载中…</p>
          ) : state.s === "miss" ? (
            <div className="note-bar" style={{ marginTop: 0 }}>
              <AlertTriangle className="ic" />
              <span>
                未定位到原文——引用片段与文档比对失败(可能文档尚未解析完成或
                引文已改写),请人工翻阅核对。
              </span>
            </div>
          ) : state.s === "err" ? (
            <div className="note-bar" style={{ marginTop: 0 }}>
              <AlertTriangle className="ic" />
              <span>{state.msg}</span>
            </div>
          ) : (
            <div className="loc-body">
              <p className="loc-meta">
                {state.data.doc.doc_id} · {state.data.doc.kind} ·{" "}
                {state.data.page != null
                  ? `第 ${state.data.page} 页`
                  : "片段窗口"}
                {quoteKey ? "(高亮为引用命中)" : ""}
              </p>
              {state.data.segments.map((sg) => {
                const hit =
                  quoteKey !== "" &&
                  sg.text.replace(/\s+/g, "").includes(quoteKey);
                return (
                  <div key={sg.seq} className={cn("loc-seg", hit && "hit")}>
                    <div className="loc-seg-hd">
                      {sg.page != null ? (
                        <span className="pill pill-gray">p.{sg.page}</span>
                      ) : null}
                      <span className="pill pill-gray">
                        {sg.kind === "table"
                          ? "表格"
                          : sg.kind === "ocr"
                            ? "OCR"
                            : "正文"}
                      </span>
                    </div>
                    <p className="loc-seg-tx">{sg.text}</p>
                    {sg.asset_id ? (
                      <img
                        className="loc-img"
                        src={docAssetUrl(taskId, target.docId, sg.asset_id)}
                        alt={`原文图片 ${sg.asset_id}`}
                        loading="lazy"
                      />
                    ) : null}
                  </div>
                );
              })}
            </div>
          )}
        </div>
        <div className="modal-ft">
          <button type="button" className="btn btn-sec" onClick={onClose}>
            关闭
          </button>
        </div>
      </div>
    </div>
  );
}
