"use client";

import {
  X,
  FileText,
  ExternalLink,
  CheckCircle,
  Loader2,
  AlertCircle,
  Calendar,
  Building2,
  Hash,
  Link2,
  Eye,
  Edit2,
  RefreshCw,
} from "lucide-react";
import React from "react";

import type { LawItem } from "@/extensions/knowledge-factory/types";

import { getCategoryByCode, getCategoryColor } from "../config/lawCategories";
import { useSyncLaw } from "../hooks/useLawLibrary";
import { cn } from "../utils";

interface LawDetailDrawerProps {
  law: LawItem;
  onClose: () => void;
  onEdit?: () => void;
}

export default function LawDetailDrawer({
  law,
  onClose,
  onEdit,
}: LawDetailDrawerProps) {
  const syncMutation = useSyncLaw();
  const category = getCategoryByCode(law.law_type);
  const { color, bgColor } = getCategoryColor(law.law_type);

  const handleSync = async () => {
    await syncMutation.mutateAsync(law.id);
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "active":
        return (
          <span className="inline-flex items-center gap-1 rounded bg-emerald-500/10 px-2 py-1 text-sm text-emerald-500">
            <CheckCircle className="h-4 w-4" /> 现行有效
          </span>
        );
      case "deprecated":
        return (
          <span className="bg-muted text-muted-foreground inline-flex items-center gap-1 rounded px-2 py-1 text-sm">
            已废止
          </span>
        );
      case "updating":
        return (
          <span className="inline-flex items-center gap-1 rounded bg-amber-500/10 px-2 py-1 text-sm text-amber-500">
            <Loader2 className="h-4 w-4 animate-spin" /> 正在修订
          </span>
        );
      default:
        return null;
    }
  };

  const getSyncBadge = (isSynced: string) => {
    switch (isSynced) {
      case "synced":
        return (
          <span className="inline-flex items-center gap-1 text-sm text-emerald-500">
            <CheckCircle className="h-4 w-4" /> 已同步到RAGFlow
          </span>
        );
      case "pending":
        return (
          <span className="inline-flex items-center gap-1 text-sm text-amber-500">
            <AlertCircle className="h-4 w-4" /> 待同步
          </span>
        );
      case "failed":
        return (
          <span className="inline-flex items-center gap-1 text-sm text-red-500">
            <AlertCircle className="h-4 w-4" /> 同步失败
          </span>
        );
      default:
        return null;
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50">
      <div
        className="bg-card animate-in slide-in-from-right flex h-full w-full max-w-2xl flex-col overflow-hidden shadow-xl duration-300"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="border-border flex shrink-0 items-center justify-between border-b p-4">
          <h3 className="text-foreground text-lg font-semibold">法规详情</h3>
          <button
            onClick={onClose}
            className="hover:bg-accent rounded-lg p-1 transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 space-y-6 overflow-y-auto p-6">
          {/* Header Info */}
          <div className="flex items-start gap-4">
            <div
              className={cn(
                "flex h-14 w-14 shrink-0 items-center justify-center rounded-xl",
                bgColor,
              )}
            >
              {category && <category.icon className={cn("h-7 w-7", color)} />}
            </div>
            <div className="min-w-0 flex-1">
              <h2 className="text-foreground text-xl font-semibold">
                {law.title}
              </h2>
              {law.law_number && (
                <p className="text-muted-foreground mt-1 flex items-center gap-1 text-sm">
                  <Hash className="h-4 w-4" /> {law.law_number}
                </p>
              )}
            </div>
          </div>

          {/* Status Badges */}
          <div className="flex flex-wrap items-center gap-3">
            {getStatusBadge(law.status)}
            {getSyncBadge(law.is_synced)}
          </div>

          {/* Basic Info */}
          <div className="space-y-4">
            <h4 className="text-foreground flex items-center gap-2 text-sm font-medium">
              <FileText className="h-4 w-4" /> 基本信息
            </h4>
            <div className="bg-muted/50 space-y-3 rounded-lg p-4">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-muted-foreground">法规类型</span>
                  <p className="text-foreground mt-0.5 font-medium">
                    {category?.name ?? law.law_type}
                  </p>
                </div>
                {law.department && (
                  <div>
                    <span className="text-muted-foreground flex items-center gap-1">
                      <Building2 className="h-4 w-4" /> 发布部门
                    </span>
                    <p className="text-foreground mt-0.5 font-medium">
                      {law.department}
                    </p>
                  </div>
                )}
                {law.effective_date && (
                  <div>
                    <span className="text-muted-foreground flex items-center gap-1">
                      <Calendar className="h-4 w-4" /> 生效日期
                    </span>
                    <p className="text-foreground mt-0.5 font-medium">
                      {new Date(law.effective_date).toLocaleDateString()}
                    </p>
                  </div>
                )}
                {law.update_date && (
                  <div>
                    <span className="text-muted-foreground">更新日期</span>
                    <p className="text-foreground mt-0.5 font-medium">
                      {new Date(law.update_date).toLocaleDateString()}
                    </p>
                  </div>
                )}
              </div>

              {/* Statistics */}
              <div className="border-border grid grid-cols-2 gap-4 border-t pt-3 text-sm">
                <div>
                  <span className="text-muted-foreground flex items-center gap-1">
                    <Eye className="h-4 w-4" /> 查看次数
                  </span>
                  <p className="text-foreground mt-0.5 font-medium">
                    {law.view_count ?? 0}
                  </p>
                </div>
                <div>
                  <span className="text-muted-foreground flex items-center gap-1">
                    <Link2 className="h-4 w-4" /> 模板引用
                  </span>
                  <p className="text-foreground mt-0.5 font-medium">
                    {law.ref_count || 0} 次
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Keywords */}
          {law.keywords && law.keywords.length > 0 && (
            <div className="space-y-3">
              <h4 className="text-foreground text-sm font-medium">
                关键词标签
              </h4>
              <div className="flex flex-wrap gap-2">
                {law.keywords.map((kw, i) => (
                  <span
                    key={i}
                    className="bg-muted rounded-lg px-3 py-1.5 text-sm"
                  >
                    {kw}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Referred Laws */}
          {law.referred_laws && law.referred_laws.length > 0 && (
            <div className="space-y-3">
              <h4 className="text-foreground text-sm font-medium">引用法规</h4>
              <div className="flex flex-wrap gap-2">
                {law.referred_laws.map((refLaw, i) => (
                  <span
                    key={i}
                    className="bg-primary/10 text-primary rounded-lg px-3 py-1.5 text-sm"
                  >
                    {refLaw}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Summary */}
          {law.summary && (
            <div className="space-y-3">
              <h4 className="text-foreground text-sm font-medium">AI摘要</h4>
              <div className="bg-muted/50 rounded-lg p-4">
                <p className="text-foreground text-sm leading-relaxed">
                  {law.summary}
                </p>
              </div>
            </div>
          )}

          {/* Linked Templates */}
          {law.linked_templates && law.linked_templates.length > 0 && (
            <div className="space-y-3">
              <h4 className="text-foreground text-sm font-medium">关联模板</h4>
              <div className="bg-muted/50 rounded-lg p-4">
                <div className="space-y-2">
                  {law.linked_templates.map((templateId, i) => (
                    <div
                      key={i}
                      className="border-border flex items-center justify-between border-b py-2 last:border-0"
                    >
                      <span className="text-foreground text-sm">
                        模板 {templateId.slice(0, 8)}...
                      </span>
                      <button className="text-primary text-sm hover:underline">
                        查看
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* RAGFlow Info */}
          {law.ragflow_document_id && (
            <div className="space-y-3">
              <h4 className="text-foreground text-sm font-medium">
                RAGFlow信息
              </h4>
              <div className="bg-muted/50 space-y-2 rounded-lg p-4 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">文档ID</span>
                  <span className="text-foreground font-mono">
                    {law.ragflow_document_id}
                  </span>
                </div>
                {law.last_sync_at && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">最后同步</span>
                    <span className="text-foreground">
                      {new Date(law.last_sync_at).toLocaleString()}
                    </span>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="border-border flex shrink-0 items-center justify-between border-t p-4">
          <div className="flex gap-2">
            <button
              onClick={handleSync}
              disabled={syncMutation.isPending}
              className="border-border hover:bg-accent flex items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors disabled:opacity-50"
            >
              {syncMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
              同步RAGFlow
            </button>
          </div>
          <div className="flex gap-2">
            {onEdit && (
              <button
                onClick={onEdit}
                className="border-border hover:bg-accent flex items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors"
              >
                <Edit2 className="h-4 w-4" />
                编辑
              </button>
            )}
            {law.source_url && (
              <a
                href={law.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="border-border hover:bg-accent flex items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors"
              >
                <ExternalLink className="h-4 w-4" />
                原文链接
              </a>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
