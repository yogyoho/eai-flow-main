"use client";

/**
 * ② 素材核对与缺口(批廿五 P1-δ 真接线)。
 *
 * 缺口清单=真实 gaps 面;素材六类实体库走 /materials CRUD + /materials/profile +
 * /policy(P1-α/β 已落地)。无「批量绑定」假按钮;绑定判定仍在断言/门禁侧。
 */

import {
  AlertTriangle,
  ArrowRight,
  Boxes,
  Info,
  PackageSearch,
  ShieldAlert,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import {
  Badge,
  EmptyState,
  ErrorBlock,
  LoadingBlock,
  MetricCell,
  MetricStrip,
  Overlay,
  PageHead,
} from "@/extensions/bid-write/components/primitives";
import { MATERIALS_COPY, STEP_BACK } from "@/extensions/bid-write/copy";
import {
  formatDate,
  gapLibraryType,
  gapStatusTone,
  matrixClauseLabel,
  matrixRequirementLabel,
  matrixStatusLabel,
  matrixStatusTone,
  sourcePathLabel,
} from "@/extensions/bid-write/helpers";
import {
  useBidWriteGaps,
  useMaterials,
  useMaterialProfile,
  usePolicy,
  usePutMaterialProfile,
  usePutPolicy,
  useSelectedWriteTask,
} from "@/extensions/bid-write/hooks";
import { WRITE_PAGE_PATHS, writeTaskHref } from "@/extensions/bid-write/nav";
import type { GapItem, PolicyBody } from "@/extensions/bid-write/types";

type Filter = "all" | "star" | "blocked" | "confirmed";

interface PolicyDraft {
  validityDays: string;
  signDate: string;
  taxRate: string;
  priceAdjust: boolean;
}

const EMPTY_POLICY: PolicyDraft = {
  validityDays: "",
  signDate: "",
  taxRate: "",
  priceAdjust: true,
};

function policyOf(raw: Record<string, unknown> | undefined): PolicyDraft {
  if (!raw) return EMPTY_POLICY;
  const letter = (raw.letter_defaults ?? null) as
    | { validity_days?: number; sign_date?: string }
    | null;
  return {
    validityDays:
      typeof letter?.validity_days === "number" ? String(letter.validity_days) : "",
    signDate: typeof letter?.sign_date === "string" ? letter.sign_date : "",
    taxRate: typeof raw.tax_rate === "number" ? String(raw.tax_rate) : "",
    priceAdjust: raw.price_adjust_mechanism !== false,
  };
}

function bodyOf(draft: PolicyDraft): PolicyBody {
  // 后端合并语义:顶层 None 键被丢弃=「不修改」;税率无清空通道(None≠删除)。
  const body: PolicyBody = {
    letter_defaults: {
      validity_days:
        draft.validityDays.trim() === "" ? undefined : Number(draft.validityDays),
      sign_date: draft.signDate.trim() === "" ? undefined : draft.signDate.trim(),
    },
    price_adjust_mechanism: draft.priceAdjust,
  };
  const tax = draft.taxRate.trim();
  if (tax !== "") body.tax_rate = Number(tax);
  return body;
}


function gapSourceLabel(item: GapItem): string {
  return sourcePathLabel(
    item.kind === "attachment"
      ? "tender.attachment_requirements"
      : "tender.required_declarations",
  );
}

export function MaterialsView() {
  const { taskId, task, isLoading } = useSelectedWriteTask();
  const gaps = useBidWriteGaps(taskId);
  const materials = useMaterials();
  const policy = usePolicy();
  const putPolicy = usePutPolicy();
  const profile = useMaterialProfile();
  const putProfile = usePutMaterialProfile();

  const [filter, setFilter] = useState<Filter>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [policyDraft, setPolicyDraft] = useState<PolicyDraft>(EMPTY_POLICY);
  const [profileText, setProfileText] = useState("{}");

  const policyLoaded = policy.data?.policy;
  useEffect(() => {
    setPolicyDraft(policyOf(policyLoaded));
  }, [policyLoaded]);

  const profileLoaded = profile.data?.profile;
  useEffect(() => {
    setProfileText(JSON.stringify(profileLoaded ?? {}, null, 2));
  }, [profileLoaded]);

  const items = useMemo(() => gaps.data?.items ?? [], [gaps.data?.items]);
  const visible = useMemo(() => {
    if (filter === "star") return items.filter((item) => item.star);
    if (filter === "blocked") return items.filter((item) => item.status === "blocked");
    if (filter === "confirmed") return items.filter((item) => item.status === "confirmed");
    return items;
  }, [filter, items]);

  useEffect(() => {
    if (selectedId && !visible.some((item) => item.clause_id === selectedId)) {
      setSelectedId(null);
    }
  }, [selectedId, visible]);

  const changeFilter = (next: Filter) => {
    setFilter(next);
    setSelectedId(null);
  };


  const selected = selectedId
    ? visible.find((item) => item.clause_id === selectedId) ?? null
    : null;
  const starCount = items.filter((item) => item.star).length;
  const blockedCount = items.filter((item) => item.status === "blocked").length;



  const onSavePolicy = async () => {
    try {
      await putPolicy.mutateAsync(bodyOf(policyDraft));
      toast.success("承诺策略已保存（只改传入键）");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "保存失败");
    }
  };

  const onSaveProfile = async () => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(profileText);
    } catch {
      toast.error("画像不是合法 JSON");
      return;
    }
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      toast.error("画像必须是 JSON 对象");
      return;
    }
    try {
      await putProfile.mutateAsync(parsed as Record<string, unknown>);
      toast.success("企业素材画像已保存");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "保存失败");
    }
  };

  return (
    <>
      <PageHead
        icon={Boxes}
        title="② 素材核对与缺口"
        subtitle={MATERIALS_COPY.subtitle}
        actions={
          <>
            {taskId && STEP_BACK.materials && (
              <Link
                href={writeTaskHref(STEP_BACK.materials, taskId)}
                className="btn btn-sm"
              >
                ← 上一步
              </Link>
            )}
            {taskId ? (
              <Link href={writeTaskHref("generate", taskId)} className="btn pri btn-sm">
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
              label="待人工核对"
              value={blockedCount}
              tone={blockedCount > 0 ? "err" : "ok"}
            />
            <MetricCell
              label="可佐证素材"
              value={(materials.data?.items ?? []).filter((item) => item.verifiable).length}
              tone="ok"
            />
          </MetricStrip>

          <div className="card bw-mt">
              <div className="card-h">
                <h3>缺口清单</h3>
                <span className="r">
                  <span className="seg">
                    <button
                      type="button"
                      className={filter === "all" ? "on" : undefined}
                      onClick={() => changeFilter("all")}
                    >
                      全部 {items.length}
                    </button>
                    <button
                      type="button"
                      className={filter === "star" ? "on" : undefined}
                      onClick={() => changeFilter("star")}
                    >
                      ★ {starCount}
                    </button>
                    <button
                      type="button"
                      className={filter === "blocked" ? "on" : undefined}
                      onClick={() => changeFilter("blocked")}
                    >
                      阻断 {blockedCount}
                    </button>
                    <button
                      type="button"
                      className={filter === "confirmed" ? "on" : undefined}
                      onClick={() => changeFilter("confirmed")}
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
                        <th>
                          矩阵状态
                          <span title={MATERIALS_COPY.statusHint}>⍰</span>
                        </th>
                        <th>
                          素材状态
                          <span title={MATERIALS_COPY.statusHint}>⍰</span>
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {visible.map((item) => (
                        <tr
                          key={item.clause_id}
                          className={`bw-gap-row ${
                            selected?.clause_id === item.clause_id ? "on" : ""
                          }`}
                          title={`查看缺口详情：${matrixClauseLabel(item.clause_id)}`}
                          onClick={() => setSelectedId(item.clause_id)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter" || event.key === " ") {
                              setSelectedId(item.clause_id);
                            }
                          }}
                          tabIndex={0}
                        >
                          <td className="mono" title={item.clause_id}>
                            {matrixClauseLabel(item.clause_id)}
                          </td>
                          <td>{gapSourceLabel(item)}</td>
                          <td>
                            <span
                              className="excerpt ellipsis"
                              title={matrixRequirementLabel(item.requirement)}
                            >
                              {item.requirement
                                ? matrixRequirementLabel(item.requirement)
                                : "（空要求）"}
                            </span>
                          </td>
                          <td>{item.star ? <span className="star">★</span> : ""}</td>
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
                    无对应素材不会阻塞矩阵确认，但会在断言执行与导出门禁中被拦截；资质素材库补录后以断言判定为准。
                  </span>
                </div>
              </div>
            </div>

          <Overlay
            open={selected !== null}
            title="缺口详情"
            subtitle={
              selected
                ? `${matrixClauseLabel(selected.clause_id)} · ${gapSourceLabel(selected)}`
                : undefined
            }
            onClose={() => setSelectedId(null)}
            footer={
              <button
                type="button"
                className="btn"
                onClick={() => setSelectedId(null)}
              >
                关闭详情
              </button>
            }
          >
            {selected ? (
              <>
                <div className="bw-drawer-summary">
                  <Badge tone={gapStatusTone(selected)} dot>
                    {selected.material_state}
                  </Badge>
                  <Badge tone={matrixStatusTone(selected)} dot>
                    {matrixStatusLabel(selected.status)}
                  </Badge>
                  {selected.star ? <Badge tone="warn">强制条款</Badge> : null}
                </div>
                <div className="kv-list">
                  <span className="k">条款</span>
                  <span className="v" title={selected.clause_id}>
                    {matrixClauseLabel(selected.clause_id)}
                  </span>
                  <span className="k">类型</span>
                  <span className="v">{gapSourceLabel(selected)}</span>
                  <span className="k">矩阵</span>
                  <span className="v">{matrixStatusLabel(selected.status)}</span>
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
                  <p>
                    {selected.requirement
                      ? matrixRequirementLabel(selected.requirement)
                      : "（空要求）"}
                  </p>
                </div>
                <div className="banner info bw-mt">
                  <Info size={15} aria-hidden="true" />
                  <span>
                    去资质素材库补录对应实体；绑定判定由断言执行与导出门禁裁决，本页不人工标记「已绑定」。
                  </span>
                  <Link
                    className="btn btn-sm"
                    href={`${WRITE_PAGE_PATHS.materials_library}?type=${encodeURIComponent(gapLibraryType(selected.requirement ?? ""))}${taskId ? `&task_id=${encodeURIComponent(taskId)}` : ""}`}
                  >
                    去资质素材库补录
                  </Link>
                </div>
              </>
            ) : null}
          </Overlay>

          <div className="bw-mt">

            <div className="card">
              <div className="card-h">
                <h3>承诺策略 policy · 企业画像</h3>
                <span className="r">
                  <Badge tone="gray">policy 只改传入键</Badge>
                </span>
              </div>
              <div className="card-b">
                <div className="bw-policy-grid">
                  <label className="field">
                    <span>投标有效期（天）</span>
                    <input
                      className="inp"
                      value={policyDraft.validityDays}
                      placeholder="如 90"
                      onChange={(event) =>
                        setPolicyDraft({ ...policyDraft, validityDays: event.target.value })
                      }
                    />
                  </label>
                  <label className="field">
                    <span>签署日期</span>
                    <input
                      className="inp"
                      value={policyDraft.signDate}
                      placeholder="2026-11-20"
                      onChange={(event) =>
                        setPolicyDraft({ ...policyDraft, signDate: event.target.value })
                      }
                    />
                  </label>
                  <label className="field">
                    <span>税率</span>
                    <input
                      className="inp"
                      value={policyDraft.taxRate}
                      placeholder="如 0.13"
                      onChange={(event) =>
                        setPolicyDraft({ ...policyDraft, taxRate: event.target.value })
                      }
                    />
                    <span className="bw-field-hint">0~1 之间；留空表示不修改</span>
                  </label>
                  <label className="bw-policy-option">
                    <input
                      type="checkbox"
                      checked={policyDraft.priceAdjust}
                      onChange={(event) =>
                        setPolicyDraft({ ...policyDraft, priceAdjust: event.target.checked })
                      }
                    />
                    <span className="t">
                      <span>报价含年度调价机制</span>
                      <span className="d">关闭后报价表按无调价机制生成，并触发 PS-009 阻断</span>
                    </span>
                  </label>
                </div>
                <div className="bw-policy-actions">
                  <button
                    type="button"
                    className="btn pri btn-sm"
                    disabled={putPolicy.isPending}
                    onClick={() => void onSavePolicy()}
                  >
                    保存策略
                  </button>
                  <span className="hint">仅提交本次填写字段；留空不会覆盖已有值</span>
                </div>
                <label className="field bw-mt">
                  <span>企业素材画像（JSON；生成面按此注入文案）</span>
                  <textarea
                    className="textarea mono"
                    rows={6}
                    value={profileText}
                    onChange={(event) => setProfileText(event.target.value)}
                  />
                </label>
                <button
                  type="button"
                  className="btn btn-sm"
                  disabled={putProfile.isPending}
                  onClick={() => void onSaveProfile()}
                >
                  保存画像
                </button>
                {profile.error ? <ErrorBlock error={profile.error} /> : null}
                <div className="banner info bw-mt">
                  <AlertTriangle size={15} aria-hidden="true" />
                  <span>
                    画像不进断言：有效性由导出门禁与 L4 审查裁决；此处只做持久化。
                  </span>
                </div>
              </div>
            </div>
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
                    <span className="mono">{gaps.data.assertions.schema_version}</span>
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
                    尚无断言执行记录。生成一次后，这里会展示待补清单、跳过注记与导出门禁。
                  </span>
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </>
  );
}
