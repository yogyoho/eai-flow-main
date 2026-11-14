"use client";

/** 批三十三：批准修订 DOCX 交付包（分册 ZIP + manifest + 导出审计）。 */

import { Download, FileArchive, PackageCheck } from "lucide-react";

import { Badge } from "@/extensions/bid-write/components/primitives";
import type {
  ApprovalRevision,
  ExportDownload,
  ExportRecord,
} from "@/extensions/bid-write/types";

interface DeliveryPackageCardProps {
  revision: ApprovalRevision | null;
  history: ExportRecord[];
  historyLoading?: boolean;
  exporting: boolean;
  result: ExportDownload | null;
  error: Error | null;
  onExport: () => void;
}

function shortHash(value: string): string {
  return value ? value.slice(0, 12) : "—";
}

function formatTime(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN");
}

export function DeliveryPackageCard({
  revision,
  history,
  historyLoading = false,
  exporting,
  result,
  error,
  onExport,
}: DeliveryPackageCardProps) {
  const approved = revision?.status === "approved" && revision.hash_ok;
  const badge = approved
    ? "已批准 · 可生成"
    : revision
      ? `修订 ${revision.revision_no} · ${revision.status}`
      : "待提交审批";

  return (
    <div className="card" data-testid="delivery-package">
      <div className="card-h">
        <h3>交付包</h3>
        <span className="r">
          <Badge tone={approved ? "ok" : "warn"} dot>
            {badge}
          </Badge>
        </span>
      </div>
      <div className="card-b">
        <p className="bw-muted">
          {approved
            ? "按一级章节分册生成 DOCX，连同 manifest.json 打包为 ZIP；导出时会对冻结修订重跑 D0/L1 门禁，未通过则拒绝生成文件。"
            : "需正文审批通过后才能生成交付包。未批准、修订哈希篡改或门禁未通过时，本页不提供下载。"}
        </p>

        {approved && revision ? (
          <p className="bw-muted">
            冻结修订 #{revision.revision_no} · 正文哈希{" "}
            <code>{shortHash(revision.doc_hash)}</code>
            {revision.decided_at ? ` · 批准于 ${formatTime(revision.decided_at)}` : ""}
          </p>
        ) : null}

        {error ? (
          <div className="banner bad bw-mt" role="alert">
            {error.message}
          </div>
        ) : null}

        {result ? (
          <div className="banner ok bw-mt" data-testid="export-result">
            <PackageCheck size={15} aria-hidden="true" />
            <span>
              已生成 {result.fileCount} 个 DOCX 分册 · 包哈希{" "}
              <code>{shortHash(result.sha256)}</code>
              {result.watermarked ? " · 含水印「商务风险未确认」" : " · 无水印"}
            </span>
          </div>
        ) : null}

        <button
          type="button"
          className="btn pri bw-full bw-mt"
          disabled={!approved || exporting}
          onClick={onExport}
          title={approved ? "生成 DOCX 分册交付包" : "需审批通过后导出"}
        >
          {exporting ? (
            <FileArchive size={14} aria-hidden="true" />
          ) : (
            <Download size={14} aria-hidden="true" />
          )}
          {exporting ? "正在生成交付包…" : "生成 DOCX 交付包"}
        </button>

        <div className="bw-mt">
          <div className="card-h">
            <h3>导出记录</h3>
            <span className="r bw-muted">
              {historyLoading ? "加载中…" : `${history.length} 次`}
            </span>
          </div>
          {history.length === 0 ? (
            <p className="bw-muted">尚无成功导出记录。</p>
          ) : (
            <ul className="gate-list">
              {history.slice(0, 5).map((item) => (
                <li key={item.id} className="pass">
                  <div>
                    <b>修订 {item.revision_id.slice(0, 8)}</b>
                    <p>
                      {item.file_count} 个文件 · {formatTime(item.created_at)} · 包哈希{" "}
                      <code>{shortHash(item.bundle_sha256)}</code>
                      {item.watermark ? ` · ${item.watermark}` : ""}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}