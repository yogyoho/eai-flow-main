"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Sparkles, Loader2 } from "lucide-react";
import { docmgrApi } from "../api";

interface AIToolbarProps {
  selectedText: string;
  fullText: string;
  onApplyResult: (text: string) => void;
}

const OPERATIONS = [
  { key: "polish", label: "润色" },
  { key: "expand", label: "扩写" },
  { key: "condense", label: "精简" },
  { key: "brainstorm", label: "头脑风暴" },
] as const;

export function AIToolbar({ selectedText, fullText, onApplyResult }: AIToolbarProps) {
  const [result, setResult] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [operation, setOperation] = useState<string | null>(null);

  const handleOperation = async (op: string) => {
    const text = selectedText || fullText;
    if (!text.trim()) return;
    setOperation(op);
    setLoading(true);
    setResult(null);
    try {
      const res = await docmgrApi.aiEdit({ text, operation: op as "polish" | "expand" | "condense" | "brainstorm" });
      setResult(res.result);
    } catch {
      setResult("AI 处理失败，请重试");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-3 space-y-3">
      <div className="flex items-center gap-2">
        <Sparkles className="w-4 h-4" />
        <span className="text-sm font-medium">AI 助手</span>
      </div>

      <div className="flex flex-wrap gap-1">
        {OPERATIONS.map((op) => (
          <Button
            key={op.key}
            size="sm"
            variant={operation === op.key ? "default" : "outline"}
            onClick={() => handleOperation(op.key)}
            disabled={loading}
          >
            {op.label}
          </Button>
        ))}
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin" />
          处理中...
        </div>
      )}

      {result && (
        <div className="space-y-2">
          <div className="p-3 rounded-md bg-muted text-sm whitespace-pre-wrap max-h-60 overflow-y-auto">
            {result}
          </div>
          <div className="flex gap-2">
            <Button size="sm" onClick={() => onApplyResult(result)}>
              应用
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setResult(null)}>
              取消
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
