"use client";

import {
  AlertTriangle,
  ArrowRight,
  Boxes,
  Info,
  PackageSearch,
  ShieldAlert,
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
import {
  formatDate,
  gapStatusTone,
  matrixStatusLabel,
  matrixStatusTone,
  sourcePathLabel,
} from "@/extensions/bid-write/helpers";
import {
  useBidWriteGaps,
  useSelectedWriteTask,
} from "@/extensions/bid-write/hooks";
import { writeTaskHref } from "@/extensions/bid-write/nav";

type Filter = "all" | "star" | "blocked" | "confirmed";

export function MaterialsView() {
  const { taskId, task, isLoading } = useSelectedWriteTask();
  const gaps = useBidWriteGaps(taskId);
  const [filter, setFilter] = useState<Filter>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const items = useMemo(() => gaps.data?.items ?? [], [gaps.data?.items]);
  const visible = useMemo(() => {
    if (filter === "star") return items.filter((item) => item.star);
    if (filter === "blocked")
      return items.filter((item) => item.status === "blocked");
    if (filter === "confirmed") {
      return items.filter((item) => item.status === "confirmed");
    }
    return items;
  }, [filter, items]);

  const selected =
    visible.find((item) => item.clause_id === selectedId) ?? visible[0] ?? null;
  const starCount = items.filter((item) => item.star).length;
  const blockedCount = items.filter((item) => item.status === "blocked").length;

  return (
    <>
      <PageHead
        icon={Boxes}
        title="② 素材核对与缺口"
        subtitle="动笔前暴露缺件 · 三态清单"
        actions={
          <>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() =>
                toast.info("素材实体库属 P1；M0 阶段没有可批量绑定的实体")
              }
            >
              批量绑定
            </button>
            {taskId ? (
              <Link
                href={writeTaskHref("generate", taskId)}
                className="btn pri btn-sm"
              >
                进入生成配置
                <ArrowRight size={13} aria-hidden="true" />
              </Link>
            ) : (
              <button type="button" className="btn pri btn-sm" disabled>
                进入生成配置
                <ArrowRight size={13} aria-hidden="true" />
              </button>
            )}
          </>
        }
      />

      {isLoading ? (
        <LoadingBlock label="正在加载任务…" />
      ) : !task ? (
        <EmptyState
          icon={Boxes}
          title="还没有写作项目"
          description="先创建项目并完成响应矩阵确认，再核对素材缺口。"
          action={
            <Link href="/bid-write" className="btn pri">
              去项目列表
            </Link>
          }
        />
      ) : gaps.isLoading ? (
        <LoadingBlock label="正在加载素材缺口…" />
      ) : gaps.error ? (
        <ErrorBlock error={gaps.error} onRetry={() => void gaps.refetch()} />
      ) : (
        <>
          <MetricStrip>
            <MetricCell label="要求项" value={items.length} accent />
            <MetricCell label="★ 强制条款" value={starCount} tone="warn" />
            <MetricCell
              label="低置信阻断"
              value={blockedCount}
              tone={blockedCount > 0 ? "err" : "ok"}
            />
            <MetricCell
              label="无对应素材"
              value={
                gaps.data?.summary.material_ready === 0 ? items.length : "—"
              }
              tone="err"
            />
            <MetricCell label="素材实体库" value="P1" suffix="未接入" />
          </MetricStrip>

          <div className="banner warn">
            <Info size={15} aria-hidden="true" />
            <span>
              <b>M0 诚实伪零：</b>
              素材六类实体库尚未落地，当前所有要求按「无对应素材」展示。
              这里不会把未核验的实体标成可佐证。
            </span>
          </div>

          <div className="split bw-materials-split bw-mt">
            <div className="card">
              <div className="card-h">
                <h3>缺口清单</h3>
                <span className="r">
                  <span className="seg">
                    <button
                      type="button"
                      className={filter === "all" ? "on" : undefined}
                      onClick={() => setFilter("all")}
                    >
                      全部 {items.length}
                    </button>
                    <button
                      type="button"
                      className={filter === "star" ? "on" : undefined}
                      onClick={() => setFilter("star")}
                    >
                      ★ {starCount}
                    </button>
                    <button
                      type="button"
                      className={filter === "blocked" ? "on" : undefined}
                      onClick={() => setFilter("blocked")}
                    >
                      阻断 {blockedCount}
                    </button>
                    <button
                      type="button"
                      className={filter === "confirmed" ? "on" : undefined}
                      onClick={() => setFilter("confirmed")}
                    >
                      已确认
                    </button>
                  </span>
                </span>
              </div>
              {visible.length === 0 ? (
                <div className="card-b">
                  <EmptyState
                    icon={PackageSearch}
                    title="当前筛选没有缺口"
                    description="切换筛选条件，或回到解析确认推进矩阵。"
                  />
                </div>
              ) : (
                <div className="tbl-wrap">
                  <table className="tbl">
                    <thead>
                      <tr>
                        <th>条款号</th>
                        <th>来源</th>
                        <th>要求</th>
                        <th>★</th>
                        <th>矩阵状态</th>
                        <th>素材状态</th>
                        <th>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visible.map((item) => (
                        <tr
                          key={item.clause_id}
                          className={
                            selected?.clause_id === item.clause_id
                              ? "on"
                              : undefined
                          }
                          onClick={() => setSelectedId(item.clause_id)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter" || event.key === " ") {
                              setSelectedId(item.clause_id);
                            }
                          }}
                          tabIndex={0}
                        >
                          <td className="mono">{item.clause_id}</td>
                          <td>
                            {sourcePathLabel(
                              item.kind === "attachment"
                                ? "tender.attachment_requirements"
                                : item.kind === "clause"
                                  ? "tender.required_declarations"
                                  : item.kind,
                            )}
                          </td>
                          <td>
                            <span
                              className="excerpt ellipsis"
                              title={item.requirement}
                            >
                              {item.requirement || "（空要求）"}
                            </span>
                          </td>
                          <td>
                            {item.star ? <span className="star">★</span> : ""}
                          </td>
                          <td>
                            <Badge tone={matrixStatusTone(item)} dot>
                              {matrixStatusLabel(item.status)}
                            </Badge>
                          </td>
                          <td>
                            <Badge tone={gapStatusTone(item)} dot>
                              {item.material_state}
                            </Badge>
                          </td>
                          <td>
                            <button
                              type="button"
                              className="btn btn-sm"
                              onClick={(event) => {
                                event.stopPropagation();
                                toast.info(
                                  "素材实体库 P1 尚未接入；当前无法补录或换用实体",
                                );
                              }}
                            >
                              查看
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <div className="card-b">
                <div className="banner bad">
                  <ShieldAlert size={15} aria-hidden="true" />
                  <span>
                    无对应素材不会阻塞「查看」与「生成配置草稿」，但会在断言执行与导出门禁中被拦截。
                  </span>
                </div>
              </div>
            </div>

            <aside className="card bw-detail-card">
              <div className="card-h">
                <h3>缺口详情</h3>
                <span className="r">
                  {selected ? (
                    <Badge tone={gapStatusTone(selected)} dot>
                      {selected.material_state}
                    </Badge>
                  ) : (
                    <Badge tone="gray">未选择</Badge>
                  )}
                </span>
              </div>
              <div className="card-b">
                {selected ? (
                  <>
                    <div className="kv-list">
                      <span className="k">条款</span>
                      <span className="v mono">{selected.clause_id}</span>
                      <span className="k">类型</span>
                      <span className="v">
                        {sourcePathLabel(
                          selected.kind === "attachment"
                            ? "tender.attachment_requirements"
                            : "tender.required_declarations",
                        )}
                      </span>
                      <span className="k">矩阵</span>
                      <span className="v">
                        {matrixStatusLabel(selected.status)}
                      </span>
                      <span className="k">★</span>
                      <span className="v">{selected.star ? "强制" : "否"}</span>
                      <span className="k">证据</span>
                      <span className="v">
                        {selected.evidence_refs.length > 0
                          ? `${selected.evidence_refs.length} 条引用`
                          : "无"}
                      </span>
                    </div>
                    <div className="bw-requirement bw-mt">
                      <span className="k">要求原文</span>
                      <p>{selected.requirement}</p>
                    </div>
                    <div className="banner info bw-mt">
                      <Info size={15} aria-hidden="true" />
                      <span>
                        P1
                        落地后，这里会显示候选实体、有效期、引用影响面，并支持换用与补录闭环。
                      </span>
                    </div>
                  </>
                ) : (
                  <EmptyState
                    icon={PackageSearch}
                    title="选择一条缺口"
                    description="左侧选择要求行后查看缺口详情。"
                  />
                )}
              </div>
            </aside>
          </div>

          <div className="card bw-mt">
            <div className="card-h">
              <h3>断言执行摘要</h3>
              <span className="r">
                {gaps.data?.assertions ? (
                  <Badge tone={gaps.data.assertions.blocked ? "bad" : "ok"} dot>
                    {gaps.data.assertions.blocked ? "导出阻断" : "可导出"}
                  </Badge>
                ) : (
                  <Badge tone="gray">尚未执行</Badge>
                )}
              </span>
            </div>
            <div className="card-b">
              {gaps.data?.assertions ? (
                <div className="bw-inline-facts">
                  <span>
                    执行时间 <b>{formatDate(gaps.data.assertions.run_at)}</b>
                  </span>
                  <span>
                    待补 <b>{gaps.data.assertions.pending.length}</b>
                  </span>
                  <span>
                    跳过 <b>{gaps.data.assertions.skipped.length}</b>
                  </span>
                  <span>
                    schema{" "}
                    <span className="mono">
                      {gaps.data.assertions.schema_version}
                    </span>
                  </span>
                  {taskId ? (
                    <Link
                      href={writeTaskHref("review", taskId)}
                      className="btn btn-sm soft bw-ml-auto"
                    >
                      查看预审查
                    </Link>
                  ) : null}
                </div>
              ) : (
                <div className="bw-inline-facts">
                  <span>
                    尚无断言执行记录。断言执行器接入后，这里会展示待补清单、跳过注记与导出门禁。
                  </span>
                </div>
              )}
            </div>
          </div>

          <div className="banner info bw-mt">
            <AlertTriangle size={15} aria-hidden="true" />
            <span>
              素材核对不是「上传即通过」：实体必须有效期覆盖投标截止日、引用可追溯，且与要求条款语义匹配。
            </span>
          </div>
        </>
      )}
    </>
  );
}
