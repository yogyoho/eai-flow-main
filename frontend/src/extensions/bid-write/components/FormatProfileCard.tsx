"use client";

import { RefreshCw, ScanText } from "lucide-react";

import {
  Badge,
  ErrorBlock,
  LoadingBlock,
} from "@/extensions/bid-write/components/primitives";
import { formatDate } from "@/extensions/bid-write/helpers";
import {
  useBidWriteFormatProfile,
  useExtractBidWriteFormatProfile,
} from "@/extensions/bid-write/hooks";

function Stat({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="bw-format-stat">
      <span>{label}</span>
      <b>{value ?? 0}</b>
    </div>
  );
}

export function FormatProfileCard({ taskId }: { taskId: string | null }) {
  const query = useBidWriteFormatProfile(taskId);
  const mutation = useExtractBidWriteFormatProfile(taskId);
  if (!taskId) return null;

  const response = query.data;
  const profile = response?.profile;
  const section = profile?.format_section;
  const gap = profile?.gap_report;
  const summary = gap?.summary ?? {};
  const blocking = gap?.blocking_gaps ?? [];
  const reasons = gap?.blocking_reasons ?? {};
  const sourceName = response?.source?.name ?? profile?.source?.name;

  return (
    <section className="card bw-format-card" aria-label="招标商务卷格式档案">
      <div className="card-h">
        <h3>招标商务卷格式档案</h3>
        <span className="hd-sub">
          按招标文件自带目录与表格提取，不套系统预置模板
        </span>
        <span className="r">
          {profile?.profile_hash ? (
            <Badge tone="gray">格式档案已提取</Badge>
          ) : null}
          <button
            type="button"
            className="btn btn-sm"
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
          >
            <RefreshCw
              size={13}
              aria-hidden="true"
              className={mutation.isPending ? "bw-spin" : undefined}
            />
            {profile ? "重新提取" : "提取格式档案"}
          </button>
        </span>
      </div>
      <div className="card-b">
        {query.isLoading ? (
          <LoadingBlock label="读取格式档案…" />
        ) : query.error ? (
          <ErrorBlock
            error={query.error}
            onRetry={() => void query.refetch()}
          />
        ) : !profile ? (
          <div className="bw-format-empty">
            <ScanText size={20} aria-hidden="true" />
            <div>
              <b>尚未提取格式档案</b>
              <p className="bw-muted">
                上传招标 DOCX 后，系统会从“投标文件格式 /
                投标文件目录”区段提取章节、表格、占位符、固定文字与签章位；未检测到格式章节时保留预置模板兜底。
              </p>
            </div>
          </div>
        ) : profile.supported === false ? (
          <ErrorBlock
            error={new Error(profile.reason ?? "该招标文件无法提取格式档案")}
          />
        ) : (
          <>
            <div className="bw-format-meta">
              <span>{sourceName ?? "招标文件"}</span>
              <span>
                {section?.detected === false
                  ? "未检测到格式章节（走预置模板兜底）"
                  : "已检测到投标文件格式章节"}
              </span>
              {response?.updated_at ? (
                <span>更新于 {formatDate(response.updated_at)}</span>
              ) : null}
            </div>
            <div className="bw-format-stats">
              <Stat label="商务卷章节" value={section?.chapter_count} />
              <Stat label="目录项" value={section?.toc_entry_count} />
              <Stat label="正文标题" value={section?.heading_count} />
              <Stat label="表格" value={summary.table_count} />
              <Stat label="合并单元格表" value={summary.merged_table_count} />
              <Stat label="占位符" value={summary.placeholder_count} />
              <Stat label="固定文字" value={summary.fixed_text_count} />
              <Stat label="签章位" value={summary.signature_count} />
              <Stat label="贴图位" value={summary.image_slot_count} />
            </div>
            {section?.chapter_titles?.length ? (
              <div className="bw-format-chapters" aria-label="招标目录章节">
                {section.chapter_titles.map((title) => (
                  <span key={title} className="bw-format-chip">
                    {title}
                  </span>
                ))}
              </div>
            ) : null}
            {gap ? (
              <div className="bw-format-gaps">
                <Badge tone={blocking.length ? "warn" : "ok"}>
                  {blocking.length
                    ? `${blocking.length} 项能力差距`
                    : "格式能力已对齐"}
                </Badge>
                {blocking.slice(0, 5).map((id) => {
                  const capability = gap.capabilities.find(
                    (item) => item.id === id,
                  );
                  return (
                    <span
                      key={id}
                      className="bw-format-chip gap"
                      title={reasons[id] ?? capability?.current_support ?? ""}
                    >
                      {capability?.label ?? id}
                    </span>
                  );
                })}
                {gap.note ? <p className="bw-muted">{gap.note}</p> : null}
              </div>
            ) : null}
          </>
        )}
        {mutation.error ? <ErrorBlock error={mutation.error} /> : null}
      </div>
    </section>
  );
}
