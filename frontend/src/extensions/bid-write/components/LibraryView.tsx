"use client";

// EAI-CUSTOM 批卅二——六类素材实体库独立页(owner 级资产;设计
// docs/superpowers/specs/2026-11-18-bid-write-materials-library-design.md)。
// 从 MaterialsView 底部区块整体迁出:六类过滤 tab + CRUD;绑定判定仍归
// 断言执行/导出门禁,本页不人工标记「已绑定」。②素材核对页经 ?type= 带实体
// 类型跳转(缺口补录上下文)。
import { Boxes, Plus, Trash2 } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Badge,
  EmptyState,
  ErrorBlock,
  LoadingBlock,
  PageHead,
} from "@/extensions/bid-write/components/primitives";
import {
  formatDate,
  MATERIAL_ENTITY_LABELS,
  materialEntityLabel,
} from "@/extensions/bid-write/helpers";
import {
  useCreateMaterial,
  useDeleteMaterial,
  useMaterials,
} from "@/extensions/bid-write/hooks";
import type { MaterialOut } from "@/extensions/bid-write/types";

function entityLabel(item: MaterialOut): string {
  return materialEntityLabel(item.entity_type);
}

export function LibraryView() {
  const search = useSearchParams();
  const initialType = search.get("type") ?? "all";
  const materials = useMaterials();
  const createMaterial = useCreateMaterial();
  const deleteMaterial = useDeleteMaterial();

  const [entityFilter, setEntityFilter] = useState<string>(
    initialType === "all" || MATERIAL_ENTITY_LABELS[initialType] ? initialType : "all",
  );
  const [newType, setNewType] = useState<string>("qualification");
  const [newName, setNewName] = useState("");

  const totalCount = materials.data?.items.length ?? 0;

  const materialRows = useMemo(() => {
    const all = materials.data?.items ?? [];
    return entityFilter === "all"
      ? all
      : all.filter((item) => item.entity_type === entityFilter);
  }, [materials.data?.items, entityFilter]);

  const onCreate = async () => {
    const name = newName.trim();
    if (!name) {
      toast.error("请填写素材名称");
      return;
    }
    try {
      await createMaterial.mutateAsync({ entity_type: newType, name, fields: {} });
      setNewName("");
      toast.success(`已添加素材「${name}」`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "添加素材失败");
    }
  };

  const onDelete = async (item: MaterialOut) => {
    try {
      await deleteMaterial.mutateAsync(item.id);
      toast.success(`已删除「${item.name}」`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "删除失败");
    }
  };

  return (
    <>
      <PageHead
        icon={Boxes}
        title="素材库"
        subtitle="六类素材实体 · owner 级资产,跨任务共用;绑定判定归断言执行与导出门禁"
      />
      <div className="card">
        <div className="card-h">
          <h3>素材实体库</h3>
          <span className="r">
            <span className="seg">
              <button
                type="button"
                className={entityFilter === "all" ? "on" : undefined}
                onClick={() => setEntityFilter("all")}
              >
                全部 {totalCount}
              </button>
              {Object.entries(MATERIAL_ENTITY_LABELS).map(([type, label]) => (
                <button
                  key={type}
                  type="button"
                  className={entityFilter === type ? "on" : undefined}
                  onClick={() => setEntityFilter(type)}
                >
                  {label}{" "}
                  {(materials.data?.items ?? []).filter((item) => item.entity_type === type).length}
                </button>
              ))}
            </span>
          </span>
        </div>
        {materials.isLoading ? (
          <div className="card-b">
            <LoadingBlock label="正在加载素材…" />
          </div>
        ) : materials.error ? (
          <div className="card-b">
            <ErrorBlock error={materials.error} onRetry={() => void materials.refetch()} />
          </div>
        ) : materialRows.length === 0 ? (
          <div className="card-b">
            <EmptyState
              icon={Boxes}
              title="没有素材实体"
              description="从下方表单补录资质、业绩、人员等六类实体；有引用的实体才可佐证（verifiable）。"
            />
          </div>
        ) : (
          <div className="tbl-wrap">
            <table className="tbl dense">
              <thead>
                <tr>
                  <th>类型</th>
                  <th>名称</th>
                  <th className="num">字段</th>
                  <th>可佐证</th>
                  <th>创建时间</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {materialRows.map((item) => (
                  <tr key={item.id}>
                    <td>{entityLabel(item)}</td>
                    <td>{item.name}</td>
                    <td className="num mono">
                      {Object.keys(item.fields ?? {}).length}
                    </td>
                    <td>
                      <Badge tone={item.verifiable ? "ok" : "gray"} dot>
                        {item.verifiable ? "有引用" : "无引用"}
                      </Badge>
                    </td>
                    <td>{formatDate(item.created_at)}</td>
                    <td>
                      <button
                        type="button"
                        className="btn btn-sm"
                        aria-label={`删除 ${item.name}`}
                        disabled={deleteMaterial.isPending}
                        onClick={() => void onDelete(item)}
                      >
                        <Trash2 size={13} aria-hidden="true" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="card-b">
          <div className="bw-inline-facts">
            <Select
              value={newType}
              onValueChange={setNewType}
            >
              <SelectTrigger
                size="sm"
                className="bw-select-trigger"
                aria-label="素材类型"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent
                className="bw-select-menu"
                position="popper"
                align="start"
                sideOffset={4}
              >
                {Object.entries(MATERIAL_ENTITY_LABELS).map(([type, label]) => (
                  <SelectItem key={type} value={type}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <input
              className="inp"
              value={newName}
              placeholder="素材名称，如 ISO9001 质量管理体系认证"
              onChange={(event) => setNewName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void onCreate();
              }}
            />
            <button
              type="button"
              className="btn pri btn-sm"
              disabled={createMaterial.isPending}
              onClick={() => void onCreate()}
            >
              <Plus size={13} aria-hidden="true" />
              添加素材
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
