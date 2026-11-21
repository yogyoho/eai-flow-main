"use client";

// EAI-CUSTOM 批卅二——资质素材库独立页(六类素材实体,owner 级资产)。
// 2026-11-18 重设计(设计稿 docs/designs/2026-11-18-bid-write-library-ui.html):
// 概览条 + 类型导航 rail(佐证率) + 佐证过滤 chips + 编辑抽屉
// (字段模板引导 + evidence_refs 行内管理;绑定判定仍归断言执行/导出门禁,
// 本页不人工标记「已绑定」)。②素材核对页经 ?type= 带实体类型跳转。
import {
  AlertTriangle,
  Award,
  Boxes,
  Briefcase,
  Check,
  Copy,
  FileText,
  Gauge,
  Map,
  PencilLine,
  Plus,
  Search,
  Trash2,
  User,
  X,
  type LucideIcon,
} from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
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
import { LIBRARY_COPY } from "@/extensions/bid-write/copy";
import {
  formatDate,
  MATERIAL_ENTITY_LABELS,
  materialEntityLabel,
  materialFieldPreview,
  materialFieldTemplate,
  materialTemplateCoverage,
} from "@/extensions/bid-write/helpers";
import {
  useCreateMaterial,
  useDeleteMaterial,
  useMaterials,
  usePatchMaterial,
} from "@/extensions/bid-write/hooks";
import type { MaterialOut } from "@/extensions/bid-write/types";

type VerFilter = "all" | "verified" | "unverified";

interface FieldRow {
  key: string;
  value: string;
}

/** 编辑抽屉状态。null=关闭;mode=edit 时 id 必有,entityType 创建后锁定。 */
interface DrawerState {
  mode: "create" | "edit";
  id?: string;
  entityType: string;
  name: string;
  fields: FieldRow[];
  refs: string[];
}

const ENTITY_ICONS: Record<string, LucideIcon> = {
  qualification: Award,
  performance: Briefcase,
  personnel: User,
  capacity: Gauge,
  network: Map,
  past_bid: FileText,
};

function entityIcon(entityType: string): LucideIcon {
  return ENTITY_ICONS[entityType] ?? Boxes;
}

/** 基本类型值转字符串;对象/数组序列化为 JSON(历史脏数据兜底,不再静默丢字段)。 */
function fieldValueText(value: unknown): string {
  if (
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  ) {
    return String(value);
  }
  return JSON.stringify(value);
}

function rowsToFields(rows: FieldRow[]): Record<string, string> {
  const fields: Record<string, string> = {};
  for (const row of rows) {
    const key = row.key.trim();
    if (!key) continue;
    fields[key] = row.value.trim();
  }
  return fields;
}

/** 搜索(P3):名称 / 字段键 / 字段值任一命中即可。 */
function matchesQuery(item: MaterialOut, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  if (item.name.toLowerCase().includes(q)) return true;
  for (const [key, value] of Object.entries(item.fields ?? {})) {
    if (key.toLowerCase().includes(q)) return true;
    if (fieldValueText(value).toLowerCase().includes(q)) return true;
  }
  return false;
}

function templateRows(entityType: string): FieldRow[] {
  return materialFieldTemplate(entityType).map((key) => ({ key, value: "" }));
}

export function LibraryView() {
  const search = useSearchParams();
  const initialType = search.get("type") ?? "all";
  const materials = useMaterials();
  const createMaterial = useCreateMaterial();
  const patchMaterial = usePatchMaterial();
  const deleteMaterial = useDeleteMaterial();

  const [entityFilter, setEntityFilter] = useState<string>(
    initialType === "all" || MATERIAL_ENTITY_LABELS[initialType]
      ? initialType
      : "all",
  );
  const [verFilter, setVerFilter] = useState<VerFilter>("all");
  const [query, setQuery] = useState("");
  const [drawer, setDrawer] = useState<DrawerState | null>(null);
  const [pendingDelete, setPendingDelete] = useState<MaterialOut | null>(null);

  const items = useMemo(
    () => materials.data?.items ?? [],
    [materials.data?.items],
  );
  const totalCount = items.length;
  const verifiedCount = items.filter((item) => item.verifiable).length;
  const unverifiedCount = totalCount - verifiedCount;
  const typesInUse = new Set(items.map((item) => item.entity_type)).size;
  const verifiedRate =
    totalCount === 0 ? 0 : Math.round((verifiedCount / totalCount) * 100);
  const coverage = useMemo(
    () => materialTemplateCoverage(items),
    [items],
  );
  const filtered = entityFilter !== "all" || verFilter !== "all" || query.trim() !== "";

  const entityTypes = Object.keys(MATERIAL_ENTITY_LABELS);
  const countOfType = (type: string) =>
    items.filter((item) => item.entity_type === type).length;
  const unverifiedOfType = (type: string) =>
    items.filter(
      (item) => item.entity_type === type && !item.verifiable,
    ).length;

  const visibleRows = useMemo(
    () =>
      items.filter((item) => {
        if (entityFilter !== "all" && item.entity_type !== entityFilter) {
          return false;
        }
        if (verFilter === "verified" && !item.verifiable) return false;
        if (verFilter === "unverified" && item.verifiable) return false;
        if (!matchesQuery(item, query)) return false;
        return true;
      }),
    [items, entityFilter, verFilter, query],
  );

  /** 历史标书复用入口(P3):复制实体引用 ent:{id},供断言槽位/写作引用。 */
  const copyEntityRef = async (item: MaterialOut) => {
    const ref = `ent:${item.id}`;
    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error("clipboard 不可用");
      }
      await navigator.clipboard.writeText(ref);
      toast.success(`已复制实体引用 ${ref}`);
    } catch {
      toast.error(`复制失败,请手动记录 ${ref}`);
    }
  };

  const openCreate = (entityType?: string) => {
    const type =
      entityType && MATERIAL_ENTITY_LABELS[entityType]
        ? entityType
        : "qualification";
    setDrawer({
      mode: "create",
      entityType: type,
      name: "",
      fields: templateRows(type),
      refs: [],
    });
  };

  const openEdit = (item: MaterialOut) => {
    setDrawer({
      mode: "edit",
      id: item.id,
      entityType: item.entity_type,
      name: item.name,
      fields: Object.entries(item.fields ?? {}).map(([key, value]) => ({
        key,
        value: fieldValueText(value),
      })),
      refs: (item.evidence_refs ?? []).map((ref) => String(ref)),
    });
  };

  const onCreate = async () => {
    if (!drawer) return;
    const name = drawer.name.trim();
    if (!name) {
      toast.error("请填写实体名称");
      return;
    }
    try {
      await createMaterial.mutateAsync({
        entity_type: drawer.entityType,
        name,
        fields: rowsToFields(drawer.fields),
        evidence_refs: drawer.refs.map((ref) => ref.trim()).filter(Boolean),
      });
      toast.success(`已添加「${name}」`);
      setDrawer(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "添加实体失败");
    }
  };

  const onSaveEdit = async () => {
    if (drawer?.mode !== "edit" || !drawer.id) return;
    const name = drawer.name.trim();
    if (!name) {
      toast.error("请填写实体名称");
      return;
    }
    try {
      await patchMaterial.mutateAsync({
        materialId: drawer.id,
        patch: {
          name,
          fields: rowsToFields(drawer.fields),
          evidence_refs: drawer.refs.map((ref) => ref.trim()).filter(Boolean),
        },
      });
      toast.success(`已保存「${name}」`);
      setDrawer(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "保存实体失败");
    }
  };

  const onDelete = async () => {
    if (!pendingDelete) return;
    try {
      await deleteMaterial.mutateAsync(pendingDelete.id);
      toast.success(`已删除「${pendingDelete.name}」`);
      setPendingDelete(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "删除失败");
    }
  };

  const drawerPending = createMaterial.isPending || patchMaterial.isPending;

  return (
    <>
      <PageHead
        icon={Boxes}
        title="资质素材库"
        subtitle={LIBRARY_COPY.subtitle}
      />

      <MetricStrip>
        <MetricCell
          label="实体总数"
          value={totalCount}
          suffix={`六类覆盖 ${typesInUse}/6`}
          accent
        />
        <MetricCell
          label="有引用(可佐证)"
          value={verifiedCount}
          suffix={totalCount > 0 ? `佐证率 ${verifiedRate}%` : undefined}
          tone="ok"
        />
        <MetricCell
          label="无引用(导出将被拦)"
          value={unverifiedCount}
          tone={unverifiedCount > 0 ? "warn" : "ok"}
        />
        <MetricCell
          label="字段完整度"
          value={`${coverage.pct}%`}
          suffix={`按类型模板 ${coverage.complete}/${coverage.counted}`}
        />
        <MetricCell label="当前过滤显示" value={visibleRows.length} />
      </MetricStrip>

      <div className="split bw-lib-split">
        <aside className="card bw-lib-rail">
          <div className="bw-lib-rail-t">实体类型</div>
          <button
            type="button"
            className={`bw-lib-rail-item ${entityFilter === "all" ? "on" : ""}`}
            onClick={() => setEntityFilter("all")}
          >
            <Boxes size={14} aria-hidden="true" />
            全部类型
            <span className="cnt">{totalCount}</span>
          </button>
          {entityTypes.map((type) => {
            const Icon = entityIcon(type);
            const count = countOfType(type);
            const unverified = unverifiedOfType(type);
            const rate =
              count === 0
                ? 0
                : Math.round(((count - unverified) / count) * 100);
            return (
              <div key={type}>
                <button
                  type="button"
                  className={`bw-lib-rail-item ${
                    entityFilter === type ? "on" : ""
                  }`}
                  onClick={() => setEntityFilter(type)}
                >
                  <Icon size={14} aria-hidden="true" />
                  {materialEntityLabel(type)}
                  <span className="cnt">{count}</span>
                  {unverified > 0 ? (
                    <span
                      className="dot-badge"
                      title={`${unverified} 条无引用`}
                    />
                  ) : null}
                </button>
                <span className="bw-lib-mini" aria-hidden="true">
                  <i style={{ width: `${rate}%` }} />
                </span>
              </div>
            );
          })}
        </aside>

        <div className="card bw-lib-main">
          <div className="card-h">
            <h3>
              {entityFilter === "all"
                ? "全部实体"
                : materialEntityLabel(entityFilter)}
            </h3>
            <span className="r">
              <div className="bw-lib-search">
                <Search size={13} aria-hidden="true" />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="搜索名称、字段…"
                  aria-label="搜索素材"
                />
              </div>
              <span className="bw-lib-chips">
                <button
                  type="button"
                  className={`bw-lib-chip ${verFilter === "all" ? "on" : ""}`}
                  onClick={() => setVerFilter("all")}
                >
                  全部 <span className="c">{totalCount}</span>
                </button>
                <button
                  type="button"
                  className={`bw-lib-chip ${verFilter === "verified" ? "on" : ""}`}
                  onClick={() => setVerFilter("verified")}
                >
                  <Check size={11} aria-hidden="true" />
                  有引用 <span className="c">{verifiedCount}</span>
                </button>
                <button
                  type="button"
                  className={`bw-lib-chip ${
                    verFilter === "unverified" ? "warn-on" : ""
                  }`}
                  onClick={() => setVerFilter("unverified")}
                >
                  <AlertTriangle size={11} aria-hidden="true" />
                  无引用 <span className="c">{unverifiedCount}</span>
                </button>
              </span>
              <button
                type="button"
                className="btn pri btn-sm"
                onClick={() =>
                  openCreate(entityFilter === "all" ? undefined : entityFilter)
                }
              >
                <Plus size={13} aria-hidden="true" />
                新建实体
              </button>
            </span>
          </div>

          {materials.isLoading ? (
            <div className="card-b">
              <LoadingBlock label="正在加载素材…" />
            </div>
          ) : materials.error ? (
            <div className="card-b">
              <ErrorBlock
                error={materials.error}
                onRetry={() => void materials.refetch()}
              />
            </div>
          ) : visibleRows.length === 0 ? (
            <div className="card-b">
              <EmptyState
                icon={Boxes}
                title={filtered ? "当前过滤没有匹配实体" : "没有素材实体"}
                description={
                  filtered
                    ? LIBRARY_COPY.emptyFiltered
                    : LIBRARY_COPY.empty
                }
              />
            </div>
          ) : (
            <div className="tbl-wrap">
              <table className="tbl dense">
                <thead>
                  <tr>
                    <th>实体 / 关键字段</th>
                    <th>类型</th>
                    <th>佐证</th>
                    <th>创建时间</th>
                    <th style={{ width: 74 }} aria-label="操作" />
                  </tr>
                </thead>
                <tbody>
                  {visibleRows.map((item) => {
                    const preview = materialFieldPreview(item.fields, 3);
                    return (
                      <tr key={item.id}>
                        <td>
                          <b>{item.name}</b>
                          {preview.length > 0 ? (
                            <div className="bw-lib-fields">
                              {preview.map(([key, value]) => (
                                <span key={key} className="chip">
                                  {key} <b>{value}</b>
                                </span>
                              ))}
                            </div>
                          ) : (
                            <div className="bw-subline">
                              暂无字段,编辑抽屉内按模板补齐
                            </div>
                          )}
                        </td>
                        <td>
                          <span className="chip">
                            {materialEntityLabel(item.entity_type)}
                          </span>
                        </td>
                        <td>
                          {item.verifiable ? (
                            <Badge tone="ok" outline>
                              {`有引用 ${(item.evidence_refs ?? []).length}`}
                            </Badge>
                          ) : (
                            <Badge tone="warn" outline icon={PencilLine}>
                              无引用
                            </Badge>
                          )}
                        </td>
                        <td>{formatDate(item.created_at)}</td>
                        <td>
                          <div className="bw-lib-row-act">
                            {item.entity_type === "past_bid" ? (
                              <button
                                type="button"
                                className="btn btn-sm"
                                aria-label={`复制实体引用 ent:${item.id}`}
                                title="复制实体引用,可在断言槽位与写作引用中使用"
                                onClick={() => void copyEntityRef(item)}
                              >
                                <Copy size={13} aria-hidden="true" />
                              </button>
                            ) : null}
                            <button
                              type="button"
                              className="btn btn-sm"
                              aria-label={`编辑 ${item.name}`}
                              onClick={() => openEdit(item)}
                            >
                              <PencilLine size={13} aria-hidden="true" />
                            </button>
                            <button
                              type="button"
                              className="btn btn-sm"
                              aria-label={`删除 ${item.name}`}
                              onClick={() => setPendingDelete(item)}
                            >
                              <Trash2 size={13} aria-hidden="true" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          <div className="card-b bw-lib-foot-hint">
            {LIBRARY_COPY.footerNote}
          </div>
        </div>
      </div>

      {/* 删除确认:实体可能被任务引用,删除前明示影响(诚实缺位口径)。 */}
      <Overlay
        open={pendingDelete !== null}
        title="删除实体"
        subtitle={pendingDelete?.name}
        onClose={() => setPendingDelete(null)}
        footer={
          <>
            <button
              type="button"
              className="btn"
              onClick={() => setPendingDelete(null)}
            >
              取消
            </button>
            <button
              type="button"
              className="btn danger"
              disabled={deleteMaterial.isPending}
              onClick={() => void onDelete()}
            >
              确认删除
            </button>
          </>
        }
      >
        {pendingDelete ? (
          <div className="banner bad">
            <AlertTriangle size={15} aria-hidden="true" />
            <span>
              将删除「{pendingDelete.name}」及其佐证引用(
              {(pendingDelete.evidence_refs ?? []).length} 条)。
              已引用该实体的任务在断言执行后转为「无对应素材」,导出会被 D0
              门禁拦截;删除前请确认没有任务正在使用。
            </span>
          </div>
        ) : null}
      </Overlay>

      {/* 新建/编辑抽屉:字段按类型模板预填;佐证引用(字符串标识,如 doc:1)行内增删。 */}
      <Overlay
        open={drawer !== null}
        variant="modal"
        size="wide"
        title={
          drawer?.mode === "edit"
            ? `编辑实体 · ${materialEntityLabel(drawer.entityType)}`
            : "新建实体"
        }
        subtitle="字段按类型模板预填;佐证引用非空即「有引用」,保存后系统自动更新佐证状态"
        onClose={() => setDrawer(null)}
        footer={
          <>
            <span className="bw-muted">
              字段值参与断言一致性校验,请与佐证原文一致
            </span>
            <span className="bw-ml-auto" />
            <button type="button" className="btn" onClick={() => setDrawer(null)}>
              取消
            </button>
            <button
              type="button"
              className="btn pri"
              disabled={drawerPending}
              onClick={() =>
                void (drawer?.mode === "edit" ? onSaveEdit() : onCreate())
              }
            >
              {drawer?.mode === "edit" ? "保存实体" : "创建实体"}
            </button>
          </>
        }
      >
        {drawer ? (
          <div className="bw-lib-drawer">
            <div className="bw-lib-fgroup">
              <span className="bw-lib-flabel">
                实体类型
                {drawer.mode === "edit" ? "(创建后锁定;如需变更请删除重建)" : ""}
              </span>
              <div
                className="bw-lib-entity-grid"
                role="radiogroup"
                aria-label="实体类型"
              >
                {entityTypes.map((type) => {
                  const Icon = entityIcon(type);
                  const on = drawer.entityType === type;
                  return (
                    <button
                      type="button"
                      key={type}
                      role="radio"
                      aria-checked={on}
                      className={`bw-lib-entity-opt ${on ? "on" : ""}`}
                      disabled={drawer.mode === "edit"}
                      onClick={() =>
                        setDrawer({
                          ...drawer,
                          entityType: type,
                          fields: templateRows(type),
                        })
                      }
                    >
                      <Icon size={14} aria-hidden="true" />
                      {materialEntityLabel(type)}
                      <small>{type}</small>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="bw-lib-fgroup">
              <label className="bw-lib-flabel" htmlFor="bw-lib-name">
                实体名称
              </label>
              <input
                id="bw-lib-name"
                className="inp bw-lib-inp"
                value={drawer.name}
                placeholder="如 ISO9001 质量管理体系认证"
                onChange={(event) =>
                  setDrawer({ ...drawer, name: event.target.value })
                }
              />
            </div>

            <div className="bw-lib-fgroup">
              <span className="bw-lib-flabel">字段(模板预填,可增删)</span>
              <div className="bw-lib-rows">
                {drawer.fields.map((row, index) => (
                  <div className="bw-lib-field-row" key={index}>
                    <input
                      className="inp bw-lib-inp"
                      value={row.key}
                      placeholder="字段名,如 证书编号"
                      aria-label={`字段名 ${index + 1}`}
                      onChange={(event) =>
                        setDrawer({
                          ...drawer,
                          fields: drawer.fields.map((r, i) =>
                            i === index
                              ? { ...r, key: event.target.value }
                              : r,
                          ),
                        })
                      }
                    />
                    <input
                      className="inp bw-lib-inp"
                      value={row.value}
                      placeholder="字段值"
                      aria-label={`字段值 ${index + 1}`}
                      onChange={(event) =>
                        setDrawer({
                          ...drawer,
                          fields: drawer.fields.map((r, i) =>
                            i === index
                              ? { ...r, value: event.target.value }
                              : r,
                          ),
                        })
                      }
                    />
                    <button
                      type="button"
                      className="bw-lib-row-del"
                      aria-label={`删除字段 ${index + 1}`}
                      onClick={() =>
                        setDrawer({
                          ...drawer,
                          fields: drawer.fields.filter(
                            (_, i) => i !== index,
                          ),
                        })
                      }
                    >
                      <X size={13} aria-hidden="true" />
                    </button>
                  </div>
                ))}
              </div>
              <button
                type="button"
                className="bw-lib-add"
                onClick={() =>
                  setDrawer({
                    ...drawer,
                    fields: [...drawer.fields, { key: "", value: "" }],
                  })
                }
              >
                <Plus size={12} aria-hidden="true" />
                添加字段
              </button>
            </div>

            <div className="bw-lib-fgroup">
              <span className="bw-lib-flabel">
                佐证引用(evidence_refs)
                <span className="bw-lib-fhint">
                  文档引用标识,如 doc:1;与素材核对文档对应
                </span>
              </span>
              <div className="bw-lib-rows">
                {drawer.refs.map((ref, index) => (
                  <div
                    className="bw-lib-field-row single"
                    key={index}
                  >
                    <input
                      className="inp bw-lib-inp"
                      value={ref}
                      placeholder="引用标识,如 doc:1"
                      aria-label={`佐证引用 ${index + 1}`}
                      onChange={(event) =>
                        setDrawer({
                          ...drawer,
                          refs: drawer.refs.map((r, i) =>
                            i === index ? event.target.value : r,
                          ),
                        })
                      }
                    />
                    <button
                      type="button"
                      className="bw-lib-row-del"
                      aria-label={`删除佐证引用 ${index + 1}`}
                      onClick={() =>
                        setDrawer({
                          ...drawer,
                          refs: drawer.refs.filter((_, i) => i !== index),
                        })
                      }
                    >
                      <X size={13} aria-hidden="true" />
                    </button>
                  </div>
                ))}
              </div>
              <button
                type="button"
                className="bw-lib-add"
                onClick={() =>
                  setDrawer({ ...drawer, refs: [...drawer.refs, ""] })
                }
              >
                <Plus size={12} aria-hidden="true" />
                添加佐证引用
              </button>
            </div>
          </div>
        ) : null}
      </Overlay>
    </>
  );
}
