"use client";

import { Check, Globe, Loader2, Play, ChevronDown, Layers, Scale } from "lucide-react";
import React, { useEffect, useRef, useState } from "react";

import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { scraperApi } from "@/extensions/api";
import { useModels } from "@/core/models/hooks";
import { getBaseSettingsSnapshot } from "@/core/settings/store";
import { useScraperContext } from "./ScraperContext";
import { cn } from "@/lib/utils";

/* ---------- Schema Dropdown ---------- */

interface SchemaItem {
  name: string;
  display_name: string;
  category: string;
}

function SchemaDropdown({ schemas, value, onChange }: { schemas: SchemaItem[]; value: string | undefined; onChange: (v: string | undefined) => void }) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const lawSchemas = schemas.filter((s) => s.category === "法规标准");
  const generalSchemas = schemas.filter((s) => s.category !== "法规标准");
  const selected = schemas.find((s) => s.name === value);

  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function handleKey(e: KeyboardEvent) { if (e.key === "Escape") setOpen(false); }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [open]);

  function pick(name: string | undefined) { onChange(name || undefined); setOpen(false); }

  const groups: { key: string; label: string; icon: React.ComponentType<{ className?: string }>; color: string; items: SchemaItem[] }[] = [];
  if (lawSchemas.length) groups.push({ key: "law", label: "法规标准", icon: Scale, color: "text-blue-500", items: lawSchemas });
  if (generalSchemas.length) groups.push({ key: "general", label: "通用模板", icon: Layers, color: "text-amber-500", items: generalSchemas });

  return (
    <div ref={containerRef} className="relative">
      <button type="button" onClick={() => setOpen(!open)} className={cn("w-full flex items-center gap-2 px-3 py-2.5 border rounded-xl text-sm bg-background shadow-sm text-left transition-all outline-none", open ? "border-primary ring-[3px] ring-primary/20" : "hover:border-primary/30 focus-visible:border-primary focus-visible:ring-primary/20 focus-visible:ring-[3px]")}>
        {selected ? (<><span className="flex-1 truncate font-medium">{selected.display_name}</span><span className="text-[10px] text-muted-foreground bg-muted/60 px-1.5 py-0.5 rounded-md font-medium">{selected.category}</span></>) : (<span className="flex-1 text-muted-foreground">无（通用提取）</span>)}
        <ChevronDown className={cn("h-4 w-4 text-muted-foreground shrink-0 transition-transform duration-200", open && "rotate-180")} />
      </button>
      {open && (
        <div className="absolute z-[60] top-full left-0 right-0 mt-1.5 bg-popover border rounded-xl shadow-lg overflow-hidden animate-in fade-in-0 slide-in-from-top-1 duration-150">
          <div className="max-h-72 overflow-auto py-1">
            <button onClick={() => pick(undefined)} className={cn("w-full flex items-center gap-2.5 px-3 py-2.5 text-sm text-left transition-colors", !value ? "bg-primary/8 text-primary font-medium" : "text-foreground hover:bg-muted/60")}>
              <div className="flex-1">通用提取</div>{!value && <Check className="h-4 w-4 text-primary shrink-0" />}
            </button>
            {groups.map((group) => {
              const GroupIcon = group.icon;
              return (
                <div key={group.key}>
                  <div className="flex items-center gap-2 px-3 pt-2 pb-1">
                    <GroupIcon className={cn("h-3.5 w-3.5", group.color)} />
                    <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">{group.label}</span>
                    <span className="flex-1 border-b border-dashed border-border" />
                  </div>
                  {group.items.map((s) => {
                    const active = value === s.name;
                    return (
                      <button key={s.name} onClick={() => pick(s.name)} className={cn("w-full flex items-center gap-2.5 pl-7 pr-3 py-2 text-sm text-left transition-colors", active ? "bg-primary/8 text-primary font-medium" : "text-foreground hover:bg-muted/60")}>
                        <span className="flex-1 truncate">{s.display_name}</span>{active && <Check className="h-4 w-4 text-primary shrink-0" />}
                      </button>
                    );
                  })}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

/* ---------- Providers ---------- */

const PROVIDERS = [
  { value: "firecrawl", label: "Firecrawl", desc: "Firecrawl API 网页抓取" },
  { value: "jina", label: "Jina", desc: "Jina Reader 网页抓取" },
];

/* ---------- Dialog Component ---------- */

export default function ScraperScrapeDialog() {
  const { scrapeDialogOpen, scrapePrefill, closeScrapeDialog, triggerTaskRefresh, setNewlyCreatedTaskId } = useScraperContext();

  const [url, setUrl] = useState("");
  const [provider, setProvider] = useState("firecrawl");
  const [schemaName, setSchemaName] = useState<string | undefined>(undefined);
  const [prompt, setPrompt] = useState("");
  const [schemas, setSchemas] = useState<SchemaItem[]>([]);
  const { models } = useModels();
  const [llmModel, setLlmModel] = useState<string | undefined>(undefined);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load schemas once
  useEffect(() => {
    scraperApi.listSchemas().then((res) => setSchemas(res.schemas || [])).catch(() => {});
  }, []);

  // Set default LLM model from settings
  useEffect(() => {
    if (models.length > 0 && !llmModel) {
      const settingsModel = getBaseSettingsSnapshot().context.model_name;
      if (settingsModel && models.some((m) => m.name === settingsModel)) {
        setLlmModel(settingsModel);
      }
    }
  }, [models, llmModel]);

  // Apply prefill when dialog opens
  useEffect(() => {
    if (scrapeDialogOpen && scrapePrefill) {
      if (scrapePrefill.url) setUrl(scrapePrefill.url);
      if (scrapePrefill.provider) setProvider(scrapePrefill.provider);
      if (scrapePrefill.schema) setSchemaName(scrapePrefill.schema);
      if (scrapePrefill.llm_model) setLlmModel(scrapePrefill.llm_model);
    }
  }, [scrapeDialogOpen, scrapePrefill]);

  // Reset form when dialog opens (without prefill)
  useEffect(() => {
    if (scrapeDialogOpen && !scrapePrefill) {
      setUrl("");
      setProvider("firecrawl");
      setSchemaName(undefined);
      setPrompt("");
      setError(null);
      const settingsModel = getBaseSettingsSnapshot().context.model_name;
      setLlmModel(settingsModel || undefined);
    }
  }, [scrapeDialogOpen, scrapePrefill]);

  async function handleSubmit() {
    if (!url.trim()) return;
    setIsSubmitting(true);
    setError(null);
    try {
      const res = await scraperApi.scrape({
        url: url.trim() as `${string}://${string}`,
        prompt: prompt || undefined,
        provider: provider as "firecrawl" | "jina",
        schema_name: schemaName || undefined,
        llm_model: llmModel || undefined,
      });
      triggerTaskRefresh();
      setNewlyCreatedTaskId(res.task_id);
      closeScrapeDialog();
    } catch (e) {
      setError(e instanceof Error ? e.message : "启动抓取失败");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <Dialog open={scrapeDialogOpen} onOpenChange={(open) => { if (!open) closeScrapeDialog(); }}>
      <DialogContent className="sm:max-w-[520px] max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Globe className="h-5 w-5 text-primary" />
            新建抓取
          </DialogTitle>
          <DialogDescription>配置参数并提交，在任务中心查看执行结果</DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* URL */}
          <div className="space-y-1.5">
            <label className="text-sm font-semibold tracking-tight">目标 URL</label>
            <div className="relative">
              <Globe className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://example.com/page"
                autoFocus
                className="w-full pl-10 pr-3 py-2.5 border rounded-xl text-sm bg-background shadow-sm focus-visible:border-primary focus-visible:ring-primary/20 focus-visible:ring-[3px] outline-none transition-all"
              />
            </div>
          </div>

          {/* Provider */}
          <div className="space-y-1.5">
            <label className="text-sm font-semibold tracking-tight">抓取引擎</label>
            <div className="grid grid-cols-2 gap-2">
              {PROVIDERS.map((p) => (
                <button
                  key={p.value}
                  type="button"
                  onClick={() => setProvider(p.value)}
                  className={cn(
                    "flex flex-col items-start px-4 py-3 rounded-xl border text-left transition-all",
                    provider === p.value ? "border-primary/30 bg-primary/5 shadow-sm" : "border-border hover:border-primary/20 hover:bg-muted/50"
                  )}
                >
                  <span className="text-sm font-medium">{p.label}</span>
                  <span className="text-xs text-muted-foreground">{p.desc}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Schema */}
          <div className="space-y-1.5">
            <label className="text-sm font-semibold tracking-tight">提取模板</label>
            <SchemaDropdown schemas={schemas} value={schemaName} onChange={setSchemaName} />
          </div>

          {/* Prompt */}
          <div className="space-y-1.5">
            <label className="text-sm font-semibold tracking-tight">提取指令</label>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="自定义提取指令（可选）..."
              rows={3}
              className="w-full px-3 py-2.5 border rounded-xl text-sm bg-background shadow-sm resize-none focus-visible:border-primary focus-visible:ring-primary/20 focus-visible:ring-[3px] outline-none transition-all"
            />
          </div>

          {/* Error */}
          {error && (
            <div className="p-3 rounded-xl bg-red-50/80 border border-red-200/60 text-red-700 text-sm flex items-start gap-2">
              <span className="shrink-0">!</span> {error}
            </div>
          )}

          {/* Submit */}
          <button
            onClick={handleSubmit}
            disabled={!url.trim() || isSubmitting}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-primary text-primary-foreground rounded-xl text-sm font-semibold hover:bg-primary/90 shadow-sm transition-all duration-200 disabled:opacity-40 disabled:pointer-events-none active:scale-[0.98]"
          >
            {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            提交抓取任务
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
