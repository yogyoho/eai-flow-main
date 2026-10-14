"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { authFetch } from "@/extensions/api/client";
import { cn } from "@/lib/utils";

interface GlossaryEntry {
  source: string;
  action: string; // force | forbid | keep
  target: string | null;
}

interface GlossaryData {
  entries: GlossaryEntry[];
  count: number;
}

export function GlossaryView() {
  const qc = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<GlossaryEntry | null>(null);
  const [notice, setNotice] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  const flash = (kind: "ok" | "err", text: string) => {
    setNotice({ kind, text });
    window.setTimeout(() => setNotice(null), 3500);
  };

  const glossaryQ = useQuery({
    queryKey: ["tlt-glossary"],
    queryFn: async (): Promise<GlossaryData> => {
      const d = await authFetch<GlossaryData>("/translation/glossary");
      return d;
    },
  });

  const entries = glossaryQ.data?.entries ?? [];

  const saveEntry = async (entry: GlossaryEntry) => {
    try {
      // 全量 PUT（术语量 ≤ 几百条无性能压力）
      const items = [...(glossaryQ.data?.entries ?? []).filter((x) => x.source !== entry.source), entry];
      await authFetch("/translation/glossary", {
        method: "PUT",
        body: JSON.stringify({ entries: items }),
      });
      void qc.invalidateQueries({ queryKey: ["tlt-glossary"] });
      flash("ok", "术语已保存");
    } catch (e) {
      flash("err", `保存失败：${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const removeEntry = async (source: string) => {
    try {
      const items = (glossaryQ.data?.entries ?? []).filter((x) => x.source !== source);
      await authFetch("/translation/glossary", {
        method: "PUT",
        body: JSON.stringify({ entries: items }),
      });
      void qc.invalidateQueries({ queryKey: ["tlt-glossary"] });
      flash("ok", "术语已删除");
    } catch (e) {
      flash("err", `删除失败：${e instanceof Error ? e.message : String(e)}`);
    }
  };

  return (
    <div className="flex h-full flex-col gap-3 p-4">
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-semibold">术语库</h1>
        <span className="text-sm text-muted-foreground">
          翻译时自动注入 · 机检术语轴核验
        </span>
        <span className="flex-1" />
        <span className="rounded-full border px-2.5 py-0.5 text-xs text-muted-foreground">
          {entries.length} 条
        </span>
        <Button size="sm" onClick={() => setEditing({ source: "", action: "force", target: "" })}>
          <Plus className="mr-1 h-3.5 w-3.5" /> 新增术语
        </Button>
      </div>

      {notice && (
        <div
          className={cn(
            "rounded-md border px-3 py-2 text-sm",
            notice.kind === "ok"
              ? "border-success/30 bg-success/10 text-success"
              : "border-destructive/30 bg-destructive/10 text-destructive",
          )}
        >
          {notice.text}
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-auto rounded-lg border">
        {glossaryQ.isLoading ? (
          <div className="flex items-center gap-2 p-4 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> 加载中…
          </div>
        ) : entries.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">
            术语库为空——机制已生效但无注入内容。样例验收闸产出后在此维护。
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50 text-left text-xs text-muted-foreground">
                <th className="px-3 py-2">源词</th>
                <th className="px-3 py-2">动作</th>
                <th className="px-3 py-2">目标译法</th>
                <th className="w-16 px-3 py-2 text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.source} className="border-b last:border-b-0 hover:bg-muted/50">
                  <td className="px-3 py-2 font-medium">{e.source}</td>
                  <td className="px-3 py-2">
                    <span
                      className={cn(
                        "rounded-full border px-2 py-0.5 text-xs",
                        e.action === "force"
                          ? "border-primary/30 bg-primary/10 text-primary"
                          : "border-muted-foreground/30 text-muted-foreground",
                      )}
                    >
                      {e.action === "force" ? "指定译法" : "保留原文"}
                    </span>
                  </td>
                  <td className="px-3 py-2">{e.target ?? "—"}</td>
                  <td className="px-3 py-2 text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0 text-destructive hover:text-destructive"
                      onClick={() => void removeEntry(e.source)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* 编辑对话框 */}
      <Dialog open={!!editing} onOpenChange={(v) => !v && setEditing(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>术语</DialogTitle>
          </DialogHeader>
          {editing && (
            <div className="flex flex-col gap-3 py-2">
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">源词 *</label>
                <Input
                  value={editing.source}
                  onChange={(e) => setEditing({ ...editing, source: e.target.value })}
                  placeholder="iron ore concentrate"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">动作</label>
                <Select
                  value={editing.action}
                  onValueChange={(v) =>
                    setEditing({ ...editing, action: v, target: v === "force" ? editing.target : "" })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="force">指定译法</SelectItem>
                    <SelectItem value="forbid">保留原文</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {editing.action === "force" && (
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">
                    目标译法 *
                  </label>
                  <Input
                    value={editing.target ?? ""}
                    onChange={(e) => setEditing({ ...editing, target: e.target.value })}
                    placeholder="铁精矿"
                  />
                </div>
              )}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>
              取消
            </Button>
            <Button
              disabled={!editing?.source.trim()}
              onClick={() => {
                if (!editing) return;
                void saveEntry(editing);
                setEditing(null);
              }}
            >
              保存
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
