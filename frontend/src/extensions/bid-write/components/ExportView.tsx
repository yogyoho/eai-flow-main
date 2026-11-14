"use client";

import {
  AlertTriangle,
  CheckCircle2,
  Download,
  FileArchive,
  Info,
  ShieldAlert,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import {
  Badge,
  EmptyState,
  ErrorBlock,
  LoadingBlock,
  MetricCell,
  MetricStrip,
  PageHead,
} from "@/extensions/bid-write/components/primitives";
import { formatDate, projectTitle } from "@/extensions/bid-write/helpers";
import {
  useBidWriteGaps,
  useSelectedWriteTask,
} from "@/extensions/bid-write/hooks";
import { writeTaskHref } from "@/extensions/bid-write/nav";

const PACKAGE_ITEMS = [
  { id: "bid_letter", name: "投标函", desc: "含报价与有效期" },
  { id: "price_sheet", name: "报价表", desc: "明细 / 汇总 / 开标一览一致" },
  { id: "response_table", name: "响应 / 偏离表", desc: "逐条响应与偏离说明" },
  { id: "attachment_index", name: "附件索引", desc: "证书、业绩与承诺函" },
  { id: "checklist", name: "投标交件检查表", desc: "签章、份数、密封与递交" },
] as const;

interface GateItem {
  id: string;
  label: string;
  detail: string;
  state: "pass" | "fail" | "unknown";
}

export function ExportView() {
  const { taskId, task, isLoading } = useSelectedWriteTask();
  const gaps = useBidWriteGaps(taskId);
  const [selected, setSelected] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(PACKAGE_ITEMS.map((item) => [item.id, true])),
  );

  const items = gaps.data?.items ?? [];
  const assertions = gaps.data?.assertions ?? null;
  const matrixBlocked = items.filter(
    (item) => item.status === "blocked",
  ).length;
  const noMaterial = items.filter(
    (item) => item.material_state === "无对应素材",
  ).length;

  const gate = useMemo<GateItem[]>(() => {
    const assertionState: GateItem["state"] = assertions
      ? assertions.blocked
        ? "fail"
        : "pass"
      : "unknown";
    return [
      {
        id: "matrix",
        label: "响应矩阵无低置信阻断",
        detail:
          matrixBlocked > 0
            ? `仍有 ${matrixBlocked} 条低置信行未确认`
            : "响应矩阵无阻断行",
        state: matrixBlocked > 0 ? "fail" : "pass",
      },
      {
        id: "assertions",
        label: "导出级断言无失败/错误",
        detail: assertions
          ? assertions.blocked
            ? `最近一次执行判定阻断，待补 ${assertions.pending.length} 条`
            : "最近一次执行未触发导出门禁"
          : "尚未执行断言，无法给出导出判定",
        state: assertionState,
      },
      {
        id: "materials",
        label: "素材缺口已处理",
        detail:
          noMaterial > 0
            ? `${noMaterial} 条要求仍无对应素材（P1 素材实体库未接入）`
            : "没有无对应素材的要求",
        state: noMaterial > 0 ? "fail" : "pass",
      },
      {
        id: "document",
        label: "正式正文版本已生成",
        detail: "生成执行管线尚未接入，没有可导出的正式正文版本",
        state: "unknown",
      },
    ];
  }, [assertions, matrixBlocked, noMaterial]);

  const failed = gate.filter((item) => item.state === "fail").length;
  const unknown = gate.filter((item) => item.state === "unknown").length;
  const canExport = failed === 0 && unknown === 0;
  const selectedCount = Object.values(selected).filter(Boolean).length;

  return (
    <>
      <PageHead
        icon={FileArchive}
        title="⑥ 导出适配"
        subtitle={
          task
            ? `${projectTitle(task)} · 门禁明确判定后才生成交付包`
            : "门禁明确判定后才生成交付包"
        }
        actions={
          <>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => toast.info("导出历史将在导出服务接入后开放")}
            >
              导出历史
            </button>
            <button
              type="button"
              className="btn pri btn-sm"
              onClick={() =>
                toast.error(
                  canExport
                    ? "导出服务尚未接入，未生成文件"
                    : "导出门禁未通过，不能生成交付包",
                )
              }
              aria-disabled={!canExport}
              title={
                canExport
                  ? "导出服务尚未接入"
                  : "导出门禁未通过，不能生成交付包"
              }
            >
              <Download size={13} aria-hidden="true" />
              生成导出包
            </button>
          </>
        }
      />

      {isLoading ? (
        <LoadingBlock label="正在加载任务…" />
      ) : !task ? (
        <EmptyState
          icon={FileArchive}
          title="还没有写作项目"
          description="先创建项目并完成写作与预审查，再进入导出。"
          action={
            <Link href="/bid-write" className="btn pri">
              去项目列表
            </Link>
          }
        />
      ) : gaps.isLoading ? (
        <LoadingBlock label="正在核验导出门禁…" />
      ) : gaps.error ? (
        <ErrorBlock error={gaps.error} onRetry={() => void gaps.refetch()} />
      ) : (
        <>
          <div
            className={`verdict ${canExport ? "clean" : failed > 0 ? "blocked" : "unrun"}`}
          >
            <span className="verdict-ic">
              {canExport ? (
                <ShieldCheck size={24} aria-hidden="true" />
              ) : failed > 0 ? (
                <XCircle size={24} aria-hidden="true" />
              ) : (
                <ShieldAlert size={24} aria-hidden="true" />
              )}
            </span>
            <div className="verdict-txt">
              <h3>
                {canExport
                  ? "门禁通过，可生成交付包"
                  : failed > 0
                    ? "导出门禁未通过"
                    : "门禁信息不完整"}
              </h3>
              <p>
                {canExport
                  ? "所有已知门禁项通过；导出服务接入后即可生成交付包。"
                  : "导出页不会绕过门禁。未满足项与未知项均保持阻断，直到后端提供确定性判定。"}
              </p>
            </div>
            <div className="verdict-meta">
              <span>失败项</span>
              <b>{failed}</b>
              <span>未知项</span>
              <b>{unknown}</b>
              {assertions ? (
                <span className="mono">{assertions.schema_version}</span>
              ) : null}
            </div>
          </div>

          <MetricStrip>
            <MetricCell
              label="门禁失败"
              value={failed}
              tone={failed > 0 ? "err" : "ok"}
              accent
            />
            <MetricCell
              label="未知项"
              value={unknown}
              tone={unknown > 0 ? "warn" : "ok"}
            />
            <MetricCell
              label="素材缺口"
              value={noMaterial}
              tone={noMaterial > 0 ? "err" : "ok"}
            />
            <MetricCell
              label="预审查执行"
              value={assertions ? formatDate(assertions.run_at) : "未执行"}
            />
          </MetricStrip>

          <div className="split bw-export-split">
            <div className="card">
              <div className="card-h">
                <h3>导出门禁</h3>
                <span className="r">
                  <Badge
                    tone={failed > 0 ? "bad" : canExport ? "ok" : "warn"}
                    dot
                  >
                    {failed > 0
                      ? `${failed} 项未通过`
                      : canExport
                        ? "全部通过"
                        : `${unknown} 项待确认`}
                  </Badge>
                </span>
              </div>
              <div className="card-b">
                <ul className="gate-list">
                  {gate.map((item) => (
                    <li key={item.id} className={item.state}>
                      <span className="gate-ic">
                        {item.state === "pass" ? (
                          <CheckCircle2 size={16} aria-hidden="true" />
                        ) : item.state === "fail" ? (
                          <XCircle size={16} aria-hidden="true" />
                        ) : (
                          <Info size={16} aria-hidden="true" />
                        )}
                      </span>
                      <div>
                        <b>{item.label}</b>
                        <p>{item.detail}</p>
                      </div>
                      {item.id === "matrix" && failed > 0 ? (
                        <Link
                          href={
                            taskId
                              ? writeTaskHref("intake", taskId)
                              : "/bid-write/intake"
                          }
                          className="btn btn-sm"
                        >
                          去确认
                        </Link>
                      ) : null}
                      {item.id === "assertions" ? (
                        <Link
                          href={
                            taskId
                              ? writeTaskHref("review", taskId)
                              : "/bid-write/review"
                          }
                          className="btn btn-sm"
                        >
                          看预审查
                        </Link>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            <div className="card">
              <div className="card-h">
                <h3>交付包内容</h3>
                <span className="r">
                  <Badge tone="gray">
                    {selectedCount} / {PACKAGE_ITEMS.length}
                  </Badge>
                </span>
              </div>
              <div className="card-b">
                <div className="pkg">
                  {PACKAGE_ITEMS.map((item) => (
                    <label
                      key={item.id}
                      className={!selected[item.id] ? "off" : undefined}
                    >
                      <input
                        type="checkbox"
                        checked={selected[item.id] ?? false}
                        onChange={(event) =>
                          setSelected((current) => ({
                            ...current,
                            [item.id]: event.target.checked,
                          }))
                        }
                      />
                      <span>
                        <b>{item.name}</b>
                        <span>{item.desc}</span>
                      </span>
                    </label>
                  ))}
                </div>
                <div className="banner info bw-mt">
                  <Info size={15} aria-hidden="true" />
                  <span>
                    导出包格式与版式适配（DOCX / PDF /
                    投标客户端导入包）需在后端导出服务中确定；
                    当前不生成任何占位文件。
                  </span>
                </div>
                <button
                  type="button"
                  className="btn pri bw-full bw-mt"
                  onClick={() =>
                    toast.error(
                      canExport
                        ? "导出服务尚未接入，未生成文件"
                        : "导出门禁未通过，不能生成交付包",
                    )
                  }
                >
                  <Download size={14} aria-hidden="true" />
                  生成导出包
                </button>
              </div>
            </div>
          </div>

          <div className="card bw-mt">
            <div className="card-h">
              <h3>导出历史</h3>
              <span className="r">
                <Badge tone="gray">暂无</Badge>
              </span>
            </div>
            <div className="card-b">
              <EmptyState
                icon={FileArchive}
                title="还没有导出记录"
                description="导出服务接入后，这里会记录版本、门禁快照、文件哈希与操作人。"
              />
            </div>
          </div>

          {failed > 0 ? (
            <div className="banner bad bw-mt">
              <AlertTriangle size={15} aria-hidden="true" />
              <span>
                只要存在失败项，导出按钮就保持不可成功；不得以「下载文件」代替门禁裁决。
              </span>
            </div>
          ) : null}
        </>
      )}
    </>
  );
}
