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

import { getCategoryByCode, getCategoryColor } from "../config/lawCategories";
import { useSyncLaw, useLinkTemplate, useUnlinkTemplate } from "../hooks/useLawLibrary";
import type { LawItem, LawType } from "@/extensions/knowledge-factory/types";
import { cn } from "../utils";

interface LawDetailDrawerProps {
  law: LawItem;
  onClose: () => void;
  onEdit?: () => void;
}

export default function LawDetailDrawer({ law, onClose, onEdit }: LawDetailDrawerProps) {
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
          <span className="inline-flex items-center gap-1 px-2 py-1 rounded text-sm bg-green-100 text-green-700">
            <CheckCircle className="w-4 h-4" /> 现行有效
          </span>
        );
      case "deprecated":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-1 rounded text-sm bg-gray-100 text-gray-600">
            已废止
          </span>
        );
      case "updating":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-1 rounded text-sm bg-amber-100 text-amber-700">
            <Loader2 className="w-4 h-4 animate-spin" /> 正在修订
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
          <span className="inline-flex items-center gap-1 text-sm text-green-600">
            <CheckCircle className="w-4 h-4" /> 已同步到RAGFlow
          </span>
        );
      case "pending":
        return (
          <span className="inline-flex items-center gap-1 text-sm text-amber-600">
            <AlertCircle className="w-4 h-4" /> 待同步
          </span>
        );
      case "failed":
        return (
          <span className="inline-flex items-center gap-1 text-sm text-red-600">
            <AlertCircle className="w-4 h-4" /> 同步失败
          </span>
        );
      default:
        return null;
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50">
      <div
        className="bg-card w-full max-w-2xl h-full overflow-hidden flex flex-col shadow-xl animate-in slide-in-from-right duration-300"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-border shrink-0">
          <h3 className="text-lg font-semibold text-foreground">法规详情</h3>
          <button
            onClick={onClose}
            className="p-1 hover:bg-accent rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Header Info */}
          <div className="flex items-start gap-4">
            <div className={cn("w-14 h-14 shrink-0 rounded-xl flex items-center justify-center", bgColor)}>
              {category && <category.icon className={cn("w-7 h-7", color)} />}
            </div>
            <div className="flex-1 min-w-0">
              <h2 className="text-xl font-semibold text-foreground">{law.title}</h2>
              {law.law_number && (
                <p className="text-sm text-muted-foreground mt-1 flex items-center gap-1">
                  <Hash className="w-4 h-4" /> {law.law_number}
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
            <h4 className="text-sm font-medium text-foreground flex items-center gap-2">
              <FileText className="w-4 h-4" /> 基本信息
            </h4>
            <div className="bg-muted/50 rounded-lg p-4 space-y-3">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-muted-foreground">法规类型</span>
                  <p className="font-medium text-foreground mt-0.5">
                    {category?.name || law.law_type}
                  </p>
                </div>
                {law.department && (
                  <div>
                    <span className="text-muted-foreground flex items-center gap-1">
                      <Building2 className="w-4 h-4" /> 发布部门
                    </span>
                    <p className="font-medium text-foreground mt-0.5">{law.department}</p>
                  </div>
                )}
                {law.effective_date && (
                  <div>
                    <span className="text-muted-foreground flex items-center gap-1">
                      <Calendar className="w-4 h-4" /> 生效日期
                    </span>
                    <p className="font-medium text-foreground mt-0.5">
                      {new Date(law.effective_date).toLocaleDateString()}
                    </p>
                  </div>
                )}
                {law.update_date && (
                  <div>
                    <span className="text-muted-foreground">更新日期</span>
                    <p className="font-medium text-foreground mt-0.5">
                      {new Date(law.update_date).toLocaleDateString()}
                    </p>
                  </div>
                )}
              </div>

              {/* Statistics */}
              <div className="grid grid-cols-2 gap-4 pt-3 border-t border-border">
                <div>
                  <span className="text-muted-foreground flex items-center gap-1">
                    <Eye className="w-4 h-4" /> 查看次数
                  </span>
                  <p className="font-medium text-foreground mt-0.5">
                    {law.view_count || 0}
                  </p>
                </div>
                <div>
                  <span className="text-muted-foreground flex items-center gap-1">
                    <Link2 className="w-4 h-4" /> 模板引用
                  </span>
                  <p className="font-medium text-foreground mt-0.5">
                    {law.ref_count || 0} 次
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Keywords */}
          {law.keywords && law.keywords.length > 0 && (
            <div className="space-y-3">
              <h4 className="text-sm font-medium text-foreground">关键词标签</h4>
              <div className="flex flex-wrap gap-2">
                {law.keywords.map((kw, i) => (
                  <span
                    key={i}
                    className="px-3 py-1.5 bg-muted text-sm rounded-lg"
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
              <h4 className="text-sm font-medium text-foreground">引用法规</h4>
              <div className="flex flex-wrap gap-2">
                {law.referred_laws.map((refLaw, i) => (
                  <span
                    key={i}
                    className="px-3 py-1.5 bg-blue-50 text-blue-700 text-sm rounded-lg"
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
              <h4 className="text-sm font-medium text-foreground">AI摘要</h4>
              <div className="bg-muted/50 rounded-lg p-4">
                <p className="text-sm text-foreground leading-relaxed">{law.summary}</p>
              </div>
            </div>
          )}

          {/* Linked Templates */}
          {law.linked_templates && law.linked_templates.length > 0 && (
            <div className="space-y-3">
              <h4 className="text-sm font-medium text-foreground">关联模板</h4>
              <div className="bg-muted/50 rounded-lg p-4">
                <div className="space-y-2">
                  {law.linked_templates.map((templateId, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between py-2 border-b border-border last:border-0"
                    >
                      <span className="text-sm text-foreground">模板 {templateId.slice(0, 8)}...</span>
                      <button className="text-sm text-primary hover:underline">
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
              <h4 className="text-sm font-medium text-foreground">RAGFlow信息</h4>
              <div className="bg-muted/50 rounded-lg p-4 text-sm space-y-2">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">文档ID</span>
                  <span className="font-mono text-foreground">
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
        <div className="flex justify-between items-center p-4 border-t border-border shrink-0">
          <div className="flex gap-2">
            <button
              onClick={handleSync}
              disabled={syncMutation.isPending}
              className="flex items-center gap-2 px-3 py-2 text-sm border border-border rounded-lg hover:bg-accent transition-colors disabled:opacity-50"
            >
              {syncMutation.isPending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <RefreshCw className="w-4 h-4" />
              )}
              同步RAGFlow
            </button>
          </div>
          <div className="flex gap-2">
            {onEdit && (
              <button
                onClick={onEdit}
                className="flex items-center gap-2 px-3 py-2 text-sm border border-border rounded-lg hover:bg-accent transition-colors"
              >
                <Edit2 className="w-4 h-4" />
                编辑
              </button>
            )}
            {law.source_url && (
              <a
                href={law.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 px-3 py-2 text-sm border border-border rounded-lg hover:bg-accent transition-colors"
              >
                <ExternalLink className="w-4 h-4" />
                原文链接
              </a>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}