"use client";

import { Sparkles, Loader2, AlertTriangle, Info, AlertCircle } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";

import { docmgrApi } from "../api";

interface AIDocumentReviewProps {
  docId: string;
  documentContent: string;
  onInsertComment: (blockId: string | null, comment: string) => void;
}

const REVIEW_TYPES = [
  { key: "full", label: "全面审查" },
  { key: "style", label: "风格检查" },
  { key: "logic", label: "逻辑审查" },
  { key: "completeness", label: "完整性检查" },
] as const;

const SEVERITY_ICONS = {
  info: Info,
  warning: AlertTriangle,
  error: AlertCircle,
};

interface AIReviewResult {
  overall_score?: number | null;
  summary?: string | null;
  comments?: Array<{ block_id?: string | null; comment: string; severity: string }>;
  error?: string;
}

export function AIDocumentReview({ docId, documentContent, onInsertComment }: AIDocumentReviewProps) {
  const [reviewType, setReviewType] = useState<string>("full");
  const [result, setResult] = useState<AIReviewResult | null>(null);
  const [loading, setLoading] = useState(false);

  const handleReview = async () => {
    setLoading(true);
    setResult(null);
    try {
      const res = await docmgrApi.aiReview({ doc_id: docId, review_type: reviewType, content: documentContent });
      setResult(res);
    } catch {
      setResult({ error: "AI 审查失败，请重试" });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Sparkles className="w-4 h-4" />
        <span className="text-sm font-medium">文档级 AI 审查</span>
      </div>

      <div className="flex flex-wrap gap-1">
        {REVIEW_TYPES.map((t) => (
          <Button
            key={t.key}
            size="sm"
            variant={reviewType === t.key ? "default" : "outline"}
            onClick={() => setReviewType(t.key)}
            disabled={loading}
          >
            {t.label}
          </Button>
        ))}
      </div>

      <Button size="sm" className="w-full" onClick={handleReview} disabled={loading}>
        {loading ? (
          <>
            <Loader2 className="w-3 h-3 mr-1 animate-spin" />
            审查中...
          </>
        ) : (
          "开始审查"
        )}
      </Button>

      {result && !result.error && (
        <div className="space-y-2">
          {result.overall_score != null && (
            <div className="text-sm">
              综合评分: <span className="font-bold text-lg">{result.overall_score}/100</span>
            </div>
          )}
          {result.summary && <p className="text-sm text-muted-foreground">{result.summary}</p>}
          {(result.comments ?? []).map((c, i: number) => {
            const Icon = SEVERITY_ICONS[c.severity as keyof typeof SEVERITY_ICONS] ?? Info;
            return (
              <div key={i} className="p-2 rounded border border-border flex gap-2">
                <Icon className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" />
                <div className="flex-1">
                  <p className="text-xs">{c.comment}</p>
                  <Button
                    size="sm"
                    variant="link"
                    className="h-auto p-0 text-[10px]"
                    onClick={() => onInsertComment(c.block_id ?? null, c.comment)}
                  >
                    插入为评论
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}
      {result?.error && <p className="text-sm text-destructive">{result.error}</p>}
    </div>
  );
}
