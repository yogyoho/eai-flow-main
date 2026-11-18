"use client";

/**
 * 定位原文 modal(EAI-CUSTOM 2026-10-30,spec D6/D8)——自 WorkbenchView 抽出共享
 * (2026-10-30 分期建议一期 s4:BaselineView 字段卡「查看原文」同用)。
 * EAI-CUSTOM (2026-10-31 二期 spec §五):正文取数+渲染抽为导出
 * {@link DocLocateBody},复核工作台(ReviewQueueView)左栏内嵌同源原文窗。
 * 证据 chip 点击 → 取命中页(pdf 真页码)或 quote ±10 段窗口(docx 无页码诚实降级);
 * 404「未定位到原文」如实呈现,不造假原文。
 */

import { AlertTriangle } from "lucide-react";
import { useEffect, useState } from "react";

import {
  type BidDocContent,
  type LocateTarget,
  docAssetUrl,
  fetchDocContent,
} from "@/extensions/bid-review/api";
import { cn } from "@/lib/utils";

/** 段内命中区段:空白折叠口径与后端定位一致(逐字比对);返回原文偏移 [start,end)
 * 供 <mark> 切分(用户反馈 2026-11-18:整段泛黄不够一目了然,要精确到句)。
 * quoteKey=两侧均已 replace(/\s+/g,"") 的摘录;无命中返回 null(段级 hit 但
 * 逐字没对上时如实不高亮,不硬造)。 */
export function locateHitRange(
  text: string,
  quoteKey: string,
): [number, number] | null {
  if (!quoteKey) return null;
  let collapsed = "";
  const origins: number[] = []; // 折叠串下标 → 原文下标
  for (let i = 0; i < text.length; i++) {
    if (/\s/.test(text.charAt(i))) continue;
    collapsed += text.charAt(i);
    origins.push(i);
  }
  const start = collapsed.indexOf(quoteKey);
  if (start < 0) return null;
  const from = origins[start];
  const to = origins[start + quoteKey.length - 1];
  if (from === undefined || to === undefined) return null;
  return [from, to + 1];
}

/** 命中段正文渲染:命中区段 <mark> 强调,其余原样(无命中整段纯文本)。 */
function SegmentText({ text, quoteKey }: { text: string; quoteKey: string }) {
  const range = locateHitRange(text, quoteKey);
  if (!range) return <p className="loc-seg-tx">{text}</p>;
  const [s, e] = range;
  return (
    <p className="loc-seg-tx">
      {text.slice(0, s)}
      <mark className="loc-hit">{text.slice(s, e)}</mark>
      {text.slice(e)}
    </p>
  );
}

/** 原文取数 + 正文渲染(加载/未命中/错误/命中段高亮);modal 与复核工作台共用。 */
export function DocLocateBody({
  taskId,
  target,
  fetchContent = fetchDocContent,
  assetUrl = docAssetUrl,
}: {
  taskId: string;
  target: LocateTarget;
  /** 数据源注入点:bid-write 溯源按钮传同口径 write 端点(fetcher 单实现律)。 */
  fetchContent?: typeof fetchDocContent;
  assetUrl?: typeof docAssetUrl;
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
    fetchContent(taskId, target.docId, {
      quote: target.page == null && target.quote ? target.quote : undefined,
      page: target.page ?? undefined,
    })
      .then((data: BidDocContent) => {
        if (alive) setState({ s: "ok", data });
      })
      .catch((e: unknown) => {
        if (!alive) return;
        // 404 判定走鸭子类型(注入的 fetcher 可能抛别的 ApiError 类——bid-write
        // 镜像端点即如此),不锁单一错误类;404 一律落诚实 miss 面。
        const status = (e as { status?: unknown } | null)?.status;
        if (status === 404) setState({ s: "miss" });
        else
          setState({
            s: "err",
            msg: e instanceof Error ? e.message : "原文取数失败",
          });
      });
    return () => {
      alive = false;
    };
  }, [taskId, target, fetchContent]);

  // 命中高亮:空白折叠后子串匹配(与后端定位口径一致)
  const quoteKey = target.quote ? target.quote.replace(/\s+/g, "") : "";

  if (state.s === "loading") {
    return <p style={{ color: "var(--text-3)", fontSize: 13 }}>原文加载中…</p>;
  }
  if (state.s === "miss") {
    return (
      <div className="note-bar" style={{ marginTop: 0 }}>
        <AlertTriangle className="ic" />
        <span>
          未定位到原文——引用片段与文档比对失败(可能文档尚未解析完成或引文已改写
          ),请人工翻阅核对。
        </span>
      </div>
    );
  }
  if (state.s === "err") {
    return (
      <div className="note-bar" style={{ marginTop: 0 }}>
        <AlertTriangle className="ic" />
        <span>{state.msg}</span>
      </div>
    );
  }
  return (
    <div className="loc-body">
      <p className="loc-meta">
        {state.data.doc.doc_id} · {state.data.doc.kind} ·{" "}
        {state.data.page != null ? `第 ${state.data.page} 页` : "片段窗口"}
        {quoteKey ? "(黄色高亮为命中摘录)" : ""}
      </p>
      {state.data.segments.map((sg) => {
        const hit =
          quoteKey !== "" && sg.text.replace(/\s+/g, "").includes(quoteKey);
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
            <SegmentText text={sg.text} quoteKey={quoteKey} />
            {sg.asset_id ? (
              <img
                className="loc-img"
                src={assetUrl(taskId, target.docId, sg.asset_id)}
                alt={`原文图片 ${sg.asset_id}`}
                loading="lazy"
              />
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

export function DocLocateModal({
  taskId,
  target,
  onClose,
}: {
  taskId: string;
  target: LocateTarget;
  onClose: () => void;
}) {
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
          <DocLocateBody taskId={taskId} target={target} />
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
