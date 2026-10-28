"use client";

/**
 * 术语库（EAI-CUSTOM，2026-10-18 语言维度 + Excel 导入 + 行内编辑）。
 *
 * 设计：docs/superpowers/specs/2026-10-18-tlt-glossary-i18n-import-design.md
 * 高保真：docs/designs/2026-10-18-translation-glossary-hifi.html
 *
 * 要点：
 * - 词条带 lang（en/fr/any）与可选 domain 标注；引擎按任务源语言注入/校验。
 * - 全表保存 + version 并发校验（409 提示刷新）。
 * - Excel/CSV 导入为合并 upsert：先预览，确认后仍走 PUT。
 */

import { useQuery } from "@tanstack/react-query";
import {
  BookMarked,
  Check,
  CircleCheck,
  ChevronDown,
  FileSpreadsheet,
  Loader2,
  Plus,
  Search,
  TriangleAlert,
  Upload,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

import {
  getGlossary,
  importGlossary,
  putGlossary,
  type GlossaryAction,
  type GlossaryEntry,
  type GlossaryImportPreview,
  type GlossaryImportRow,
  type GlossaryLang,
} from "../api";

import { PageHeader } from "./PageHeader";
import { NoteBar, Pill } from "./ui/bits";

const LANG_OPTIONS: { value: GlossaryLang; label: string }[] = [
  { value: "en", label: "EN · 英文" },
  { value: "fr", label: "FR · 法文" },
  { value: "any", label: "ANY · 英法通用" },
];

const ACTION_OPTIONS: { value: GlossaryAction; label: string }[] = [
  { value: "force", label: "指定译法" },
  { value: "forbid", label: "保留原文" },
  { value: "keep", label: "原样保留" },
];

const KEY = (e: GlossaryEntry) => `${e.lang}:${e.source.trim().toLowerCase()}`;

const emptyEntry = (): GlossaryEntry => ({
  source: "",
  lang: "en",
  action: "force",
  target: null,
  domains: [],
  notes: null,
});

const LANG_BADGE: Record<GlossaryLang, string> = {
  en: "border-primary/20 bg-primary/10 text-primary",
  fr: "border-info/25 bg-info/10 text-[var(--info-900)]",
  any: "border-border bg-muted/50 text-muted-foreground",
};

const GREEN_CHIP =
  "border-[var(--success-100)] bg-[var(--success-50)] text-[var(--success-700)]";

function LangBadge({ lang }: { lang: GlossaryLang }) {
  return (
    <span
      className={cn(
        "inline-flex h-5 min-w-10 items-center justify-center rounded border px-1.5 font-mono text-[11px] font-semibold tracking-wide",
        LANG_BADGE[lang],
      )}
    >
      {lang.toUpperCase()}
    </span>
  );
}

function ActionPill({ action }: { action: GlossaryAction }) {
  if (action === "force") return <Pill tone="primary">指定译法</Pill>;
  if (action === "keep") return <Pill tone="info">原样保留</Pill>;
  return <Pill tone="gray">保留原文</Pill>;
}

function ImportStatusPill({ status }: { status: GlossaryImportRow["status"] }) {
  if (status === "add") return <Pill tone="primary">新增</Pill>;
  if (status === "update") return <Pill tone="warn">更新</Pill>;
  if (status === "invalid") return <Pill tone="error">错误</Pill>;
  return <Pill tone="gray">无变化</Pill>;
}

/** 领域标签输入：输入文字 + Enter 生成 chip；Backspace 删除末尾 chip。 */
function TagInput({
  value,
  onChange,
  placeholder,
  ariaLabel,
}: {
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  ariaLabel: string;
}) {
  const [text, setText] = useState("");

  const addTag = () => {
    const tag = text.trim();
    if (!tag) return;
    if (!value.some((item) => item.toLowerCase() === tag.toLowerCase())) {
      onChange([...value, tag]);
    }
    setText("");
  };

  return (
    <div className="border-input bg-background flex min-h-7 w-full flex-wrap items-center gap-1 rounded-md border px-1.5 py-1">
      {value.map((tag) => (
        <span
          key={tag}
          className="bg-muted text-muted-foreground inline-flex h-5 items-center gap-0.5 rounded px-1.5 text-[11px]"
        >
          {tag}
          <button
            type="button"
            aria-label={`移除领域 ${tag}`}
            className="hover:text-foreground"
            onClick={() => onChange(value.filter((item) => item !== tag))}
          >
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}
      <input
        aria-label={ariaLabel}
        className="h-5 min-w-16 flex-1 bg-transparent text-xs outline-none"
        value={text}
        placeholder={value.length === 0 ? placeholder : undefined}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            e.stopPropagation();
            addTag();
          } else if (e.key === "Backspace" && !text && value.length > 0) {
            e.preventDefault();
            e.stopPropagation();
            onChange(value.slice(0, -1));
          }
        }}
      />
    </div>
  );
}

export function GlossaryView() {
  const glossaryQ = useQuery({
    queryKey: ["tlt-glossary"],
    queryFn: getGlossary,
  });

  const [entries, setEntries] = useState<GlossaryEntry[]>([]);
  const [version, setVersion] = useState("");
  const [saving, setSaving] = useState(false);

  const [langFilter, setLangFilter] = useState<"all" | GlossaryLang>("all");
  const [domainFilters, setDomainFilters] = useState<string[]>([]);
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState<GlossaryEntry | null>(null);

  const [addOpen, setAddOpen] = useState(false);
  const [addDraft, setAddDraft] = useState<GlossaryEntry>(emptyEntry());

  const [importOpen, setImportOpen] = useState(false);
  const [importPreview, setImportPreview] =
    useState<GlossaryImportPreview | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [importFileName, setImportFileName] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!glossaryQ.data) return;
    setEntries(glossaryQ.data.entries);
    setVersion(glossaryQ.data.version);
  }, [glossaryQ.data]);

  const counts = useMemo(
    () => ({
      all: entries.length,
      en: entries.filter((e) => e.lang === "en").length,
      fr: entries.filter((e) => e.lang === "fr").length,
      any: entries.filter((e) => e.lang === "any").length,
    }),
    [entries],
  );

  const domains = useMemo(
    () => Array.from(new Set(entries.flatMap((entry) => entry.domains))).sort(),
    [entries],
  );

  const visible = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return entries.filter((entry) => {
      if (langFilter !== "all" && entry.lang !== langFilter) return false;
      if (
        domainFilters.length > 0 &&
        !entry.domains.some((domain) => domainFilters.includes(domain))
      ) {
        return false;
      }
      if (!needle) return true;
      return `${entry.source} ${entry.target ?? ""} ${entry.domains.join(" ")} ${entry.notes ?? ""}`
        .toLowerCase()
        .includes(needle);
    });
  }, [entries, langFilter, domainFilters, q]);

  const pageCount = Math.max(1, Math.ceil(visible.length / pageSize));

  useEffect(() => {
    if (page > pageCount) setPage(pageCount);
  }, [page, pageCount]);

  const paged = useMemo(
    () => visible.slice((page - 1) * pageSize, page * pageSize),
    [visible, page, pageSize],
  );

  /** 全表保存；409 时提示并刷新，保留当前编辑态供重试。 */
  const persist = async (
    next: GlossaryEntry[],
    okText: string,
    baseVersion: string = version,
  ): Promise<boolean> => {
    setSaving(true);
    try {
      const res = await putGlossary(next, baseVersion);
      setEntries(res.entries);
      setVersion(res.version);
      toast.success(okText);
      return true;
    } catch (e) {
      if ((e as { status?: number }).status === 409) {
        toast.error("术语库已被他人修改，已刷新，请重试");
        void glossaryQ.refetch();
      } else {
        toast.error(e instanceof Error ? e.message : String(e));
      }
      return false;
    } finally {
      setSaving(false);
    }
  };

  const startEdit = (entry: GlossaryEntry) => {
    setEditDraft({ ...entry });
    setEditingKey(KEY(entry));
  };

  const cancelEdit = () => {
    setEditingKey(null);
    setEditDraft(null);
  };

  const updateDraft = (patch: Partial<GlossaryEntry>) => {
    setEditDraft((draft) => (draft ? { ...draft, ...patch } : draft));
  };

  const normalize = (draft: GlossaryEntry): GlossaryEntry | null => {
    const source = draft.source.trim();
    const target = (draft.target ?? "").trim() || null;
    if (!source) {
      toast.error("源词不能为空");
      return null;
    }
    if (draft.action === "force" && !target) {
      toast.error("指定译法缺少目标译法");
      return null;
    }
    return {
      source,
      lang: draft.lang,
      action: draft.action,
      target: draft.action === "force" ? target : null,
      domains: Array.from(
        new Set(draft.domains.map((domain) => domain.trim()).filter(Boolean)),
      ),
      notes: (draft.notes ?? "").trim() || null,
    };
  };

  const saveEdit = async () => {
    if (!editDraft || editingKey === null) return;
    const normalized = normalize(editDraft);
    if (!normalized) return;

    const originalIndex = entries.findIndex((e) => KEY(e) === editingKey);
    if (originalIndex < 0) {
      cancelEdit();
      return;
    }
    const next = entries.map((entry, index) =>
      index === originalIndex ? normalized : entry,
    );
    const key = KEY(normalized);
    if (next.some((entry, index) => index !== originalIndex && KEY(entry) === key)) {
      toast.error("同一源词与语言只允许一条");
      return;
    }
    if (await persist(next, "术语已保存")) cancelEdit();
  };

  const remove = async (entry: GlossaryEntry) => {
    if (!window.confirm(`删除术语「${entry.source}」？`)) return;
    const next = entries.filter((e) => KEY(e) !== KEY(entry));
    await persist(next, "术语已删除");
  };

  const openAdd = () => {
    setAddDraft(emptyEntry());
    setAddOpen(true);
  };

  const saveAdd = async () => {
    const normalized = normalize(addDraft);
    if (!normalized) return;
    const key = KEY(normalized);
    if (entries.some((entry) => KEY(entry) === key)) {
      toast.error("同一源词与语言只允许一条");
      return;
    }
    if (await persist([...entries, normalized], "术语已新增")) setAddOpen(false);
  };

  const openImport = () => {
    setImportPreview(null);
    setImportError(null);
    setImportFileName("");
    setImportOpen(true);
  };

  const handleFile = async (file: File | undefined) => {
    if (!file) return;
    setImportFileName(file.name);
    setImporting(true);
    setImportError(null);
    try {
      setImportPreview(await importGlossary(file));
    } catch (e) {
      setImportPreview(null);
      setImportError(e instanceof Error ? e.message : String(e));
    } finally {
      setImporting(false);
    }
  };

  const invalidCount =
    importPreview?.rows.filter((row) => row.status === "invalid").length ?? 0;

  const confirmImport = async () => {
    if (!importPreview || invalidCount > 0) return;
    const ok = await persist(
      importPreview.merged_entries,
      `已导入 ${importPreview.merged_entries.length} 条术语`,
      importPreview.version,
    );
    if (ok) {
      setImportOpen(false);
      setImportPreview(null);
      setImportFileName("");
    }
  };

  /** 更新行在预览里展示旧译法（来自当前表）。 */
  const oldTargetOf = (row: GlossaryImportRow): string | null => {
    const old = entries.find(
      (entry) =>
        entry.lang === row.lang &&
        entry.source.trim().toLowerCase() === row.source.trim().toLowerCase(),
    );
    return old?.target ?? null;
  };

  const TableSkeleton = () => (
    <div role="status" aria-label="术语列表加载中">
      <table className="w-full table-fixed border-collapse text-left" aria-hidden>
        <thead>
          <tr className="bg-muted/50 border-b">
            {["源词", "语言", "动作", "目标译法", "领域", "说明", "操作"].map(
              (h) => (
                <th
                  key={h}
                  className="text-muted-foreground px-3 py-2.5 text-xs font-medium"
                >
                  {h}
                </th>
              ),
            )}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: 6 }, (_, i) => (
            <tr
              key={i}
              className="border-b border-[var(--gray-100)] last:border-b-0"
            >
              <td className="px-3 py-2">
                <div
                  className="bg-muted-foreground/15 h-3.5 animate-pulse rounded"
                  style={{ width: 100 + (i % 3) * 40 }}
                />
              </td>
              <td className="px-3 py-2">
                <div className="bg-muted-foreground/15 h-5 w-10 animate-pulse rounded" />
              </td>
              <td className="px-3 py-2">
                <div className="bg-muted-foreground/15 h-5 w-16 animate-pulse rounded-full" />
              </td>
              <td className="px-3 py-2">
                <div
                  className="bg-muted-foreground/15 h-3.5 animate-pulse rounded"
                  style={{ width: 70 + (i % 4) * 24 }}
                />
              </td>
              <td className="px-3 py-2">
                <div className="bg-muted-foreground/15 h-3.5 w-16 animate-pulse rounded" />
              </td>
              <td className="px-3 py-2" />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  return (
    <div className="flex h-full flex-col gap-3 overflow-y-auto px-4 pt-3 pb-4">
      <PageHeader
        title="术语库"
        description="按源语言注入 · 术语轴硬校验 · 同一源词同一语言唯一目标"
        icon={<BookMarked />}
        actions={
          <>
            <Pill tone="gray">{entries.length} 条</Pill>
            <Button
              variant="outline"
              size="sm"
              className="text-[13px]"
              onClick={openImport}
            >
              <Upload className="mr-1 h-3.5 w-3.5" /> 导入 Excel
            </Button>
            <Button size="sm" className="text-[13px]" onClick={openAdd}>
              <Plus className="mr-1 h-3.5 w-3.5" /> 新增术语
            </Button>
          </>
        }
      />

      <section className="bg-card border-border flex shrink-0 flex-col overflow-hidden rounded-lg border">
        <div className="border-border flex flex-wrap items-center gap-2 border-b px-4 py-3">
          <h2 className="text-foreground text-sm font-semibold">术语表</h2>
          <span className="text-muted-foreground text-xs">
            英文/法文各自成组 · ANY 用于公司名与缩写
          </span>
          <div className="ml-auto">
            <Pill tone="success" className={GREEN_CHIP}>
              <CircleCheck className="h-3.5 w-3.5 text-[var(--success-500)]" />
              已自动保存
            </Pill>
          </div>
        </div>

        <div className="border-border flex flex-wrap items-center gap-2 border-b px-4 py-2.5">
          {(
            [
              ["all", "全部", counts.all],
              ["en", "EN", counts.en],
              ["fr", "FR", counts.fr],
              ["any", "ANY", counts.any],
            ] as const
          ).map(([value, label, count]) => (
            <button
              key={value}
              onClick={() => {
                setLangFilter(value);
                setPage(1);
              }}
              className={cn(
                "inline-flex h-6 items-center gap-1 rounded-full border px-2.5 text-xs transition-colors",
                langFilter === value
                  ? "border-primary/40 bg-primary/10 text-primary"
                  : "border-border text-muted-foreground hover:border-primary/30",
              )}
            >
              {label}
              <b className="font-mono text-[10px] tabular-nums">{count}</b>
            </button>
          ))}

          <div className="relative">
            <Search className="text-muted-foreground absolute top-2 left-2.5 h-4 w-4" />
            <Input
              className="h-8 w-[220px] pl-8 text-xs"
              placeholder="搜索源词 / 目标译法"
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setPage(1);
              }}
            />
          </div>

          <Popover>
            <PopoverTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                className="h-8 w-36 justify-between px-2.5 text-xs font-normal"
              >
                <span className="truncate">
                  {domainFilters.length === 0
                    ? "全部领域"
                    : `领域 · ${domainFilters.length}`}
                </span>
                <ChevronDown className="h-3.5 w-3.5 opacity-50" />
              </Button>
            </PopoverTrigger>
            <PopoverContent align="start" className="w-56 p-1">
              <button
                type="button"
                className="hover:bg-muted flex w-full items-center justify-between rounded px-2 py-1.5 text-xs"
                onClick={() => {
                  setDomainFilters([]);
                  setPage(1);
                }}
              >
                全部领域
                {domainFilters.length === 0 && <Check className="h-3.5 w-3.5" />}
              </button>
              <div className="border-border my-1 border-t" />
              <div className="max-h-60 overflow-y-auto">
                {domains.map((domain) => {
                  const checked = domainFilters.includes(domain);
                  return (
                    <label
                      key={domain}
                      className="hover:bg-muted flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-xs"
                    >
                      <Checkbox
                        checked={checked}
                        onCheckedChange={(next) => {
                          setDomainFilters((prev) =>
                            next
                              ? prev.includes(domain)
                                ? prev
                                : [...prev, domain]
                              : prev.filter((item) => item !== domain),
                          );
                          setPage(1);
                        }}
                      />
                      <span className="truncate">{domain}</span>
                    </label>
                  );
                })}
                {domains.length === 0 && (
                  <p className="text-muted-foreground px-2 py-2 text-xs">
                    暂无领域标签
                  </p>
                )}
              </div>
            </PopoverContent>
          </Popover>

          <span className="flex-1" />
          <span className="text-muted-foreground text-[11px]">
            版本{" "}
            <span className="font-mono">
              {version ? version.slice(0, 6) : "—"}
            </span>
          </span>
        </div>

        <div className="overflow-x-auto">
          {glossaryQ.isLoading ? (
            <TableSkeleton />
          ) : entries.length === 0 ? (
            <div className="text-muted-foreground flex flex-col items-center justify-center gap-2 p-10 text-center text-sm">
              <BookMarked className="h-10 w-10" />
              <p>术语库为空——机制已生效但无注入内容。</p>
              <p className="text-xs">
                从 Excel 导入，或新增术语开始维护。
              </p>
            </div>
          ) : (
            <table className="w-full table-fixed border-collapse text-left">
              <thead>
                <tr className="bg-muted/50 border-b">
                  <th className="text-muted-foreground w-[24%] px-3 py-2.5 text-xs font-medium">
                    源词
                  </th>
                  <th className="text-muted-foreground w-24 px-3 py-2.5 text-xs font-medium">
                    语言
                  </th>
                  <th className="text-muted-foreground w-32 px-3 py-2.5 text-xs font-medium">
                    动作
                  </th>
                  <th className="text-muted-foreground w-[16%] px-3 py-2.5 text-xs font-medium">
                    目标译法
                  </th>
                  <th className="text-muted-foreground w-[15%] px-3 py-2.5 text-xs font-medium">
                    领域
                  </th>
                  <th className="text-muted-foreground w-[15%] px-3 py-2.5 text-xs font-medium">
                    说明
                  </th>
                  <th className="text-muted-foreground w-32 px-3 py-2.5 text-right text-xs font-medium">
                    操作
                  </th>
                </tr>
              </thead>
              <tbody>
                {paged.map((entry) => {
                  const key = KEY(entry);
                  const draft = editingKey === key ? editDraft : null;
                  const isEditing = Boolean(draft);
                  const targetDisabled = draft?.action !== "force";
                  return (
                    <tr
                      key={key}
                      className={cn(
                        "border-b border-[var(--gray-100)] transition-colors last:border-b-0",
                        isEditing
                          ? "bg-primary/5"
                          : "hover:bg-muted/40",
                      )}
                      onKeyDown={(e) => {
                        if (!isEditing) return;
                        if (
                          e.key === "Enter" &&
                          e.target instanceof HTMLInputElement
                        ) {
                          e.preventDefault();
                          void saveEdit();
                        } else if (e.key === "Escape") {
                          e.preventDefault();
                          cancelEdit();
                        }
                      }}
                    >
                      {draft ? (
                        <>
                          <td className="px-3 py-1.5">
                            <Input
                              autoFocus
                              className="h-7 font-mono text-xs"
                              value={draft.source}
                              aria-label="源词"
                              onChange={(e) =>
                                updateDraft({ source: e.target.value })
                              }
                            />
                          </td>
                          <td className="px-3 py-1.5">
                            <Select
                              value={draft.lang}
                              onValueChange={(v) =>
                                updateDraft({ lang: v as GlossaryLang })
                              }
                            >
                              <SelectTrigger
                                size="sm"
                                className="h-7 w-full px-1.5 text-xs"
                              >
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                {LANG_OPTIONS.map((option) => (
                                  <SelectItem
                                    key={option.value}
                                    value={option.value}
                                  >
                                    {option.value.toUpperCase()}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </td>
                          <td className="px-3 py-1.5">
                            <Select
                              value={draft.action}
                              onValueChange={(v) => {
                                const action = v as GlossaryAction;
                                updateDraft({
                                  action,
                                  target:
                                    action === "force" ? draft.target : null,
                                });
                              }}
                            >
                              <SelectTrigger
                                size="sm"
                                className="h-7 w-full px-1.5 text-xs"
                              >
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                {ACTION_OPTIONS.map((option) => (
                                  <SelectItem
                                    key={option.value}
                                    value={option.value}
                                  >
                                    {option.label}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </td>
                          <td className="px-3 py-1.5">
                            <Input
                              className="h-7 text-xs"
                              value={draft.target ?? ""}
                              disabled={targetDisabled}
                              aria-label="目标译法"
                              onChange={(e) =>
                                updateDraft({ target: e.target.value || null })
                              }
                            />
                          </td>
                          <td className="px-3 py-1.5">
                            <TagInput
                              value={draft.domains}
                              onChange={(domains) => updateDraft({ domains })}
                              placeholder="输入后回车"
                              ariaLabel="业务领域标签"
                            />
                          </td>
                          <td className="px-3 py-1.5">
                            <Input
                              className="h-7 text-xs"
                              value={draft.notes ?? ""}
                              placeholder="说明（可选）"
                              aria-label="说明"
                              onChange={(e) =>
                                updateDraft({ notes: e.target.value || null })
                              }
                            />
                          </td>
                          <td className="px-3 py-1.5">
                            <div className="flex flex-col items-end gap-0.5">
                              <div className="flex items-center gap-1">
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-6 px-2 text-xs"
                                  disabled={saving}
                                  onClick={() => void saveEdit()}
                                >
                                  保存
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-6 px-2 text-xs"
                                  onClick={cancelEdit}
                                >
                                  取消
                                </Button>
                              </div>
                              <span className="text-muted-foreground text-[10px] whitespace-nowrap">
                                Enter 保存 · Esc 取消
                              </span>
                            </div>
                          </td>
                        </>
                      ) : (
                        <>
                          <td className="px-3 py-2 font-mono text-[12.5px] font-medium">
                            {entry.source}
                          </td>
                          <td className="px-3 py-2">
                            <LangBadge lang={entry.lang} />
                          </td>
                          <td className="px-3 py-2">
                            <ActionPill action={entry.action} />
                          </td>
                          <td className="px-3 py-2 text-[13px]">
                            {entry.target ?? (
                              <span className="text-muted-foreground">—</span>
                            )}
                          </td>
                          <td className="px-3 py-2">
                            {entry.domains.length > 0 ? (
                              <div className="flex flex-wrap gap-1">
                                {entry.domains.map((domain) => (
                                  <span
                                    key={domain}
                                    className="border-border bg-muted/50 text-muted-foreground inline-flex h-5 items-center rounded border px-1.5 text-[11px]"
                                  >
                                    {domain}
                                  </span>
                                ))}
                              </div>
                            ) : (
                              <span className="text-muted-foreground text-xs">
                                —
                              </span>
                            )}
                          </td>
                          <td className="text-muted-foreground px-3 py-2 text-xs">
                            {entry.notes ? (
                              <span
                                className="line-clamp-2 break-words"
                                title={entry.notes}
                              >
                                {entry.notes}
                              </span>
                            ) : (
                              "—"
                            )}
                          </td>
                          <td className="px-3 py-2">
                            <div className="flex items-center justify-end gap-1">
                              <button
                                className="text-muted-foreground hover:bg-muted hover:text-foreground rounded px-1.5 py-0.5 text-[13px] whitespace-nowrap transition-colors"
                                onClick={() => startEdit(entry)}
                              >
                                编辑
                              </button>
                              <button
                                className="text-destructive hover:bg-destructive/10 rounded px-1.5 py-0.5 text-[13px] whitespace-nowrap transition-colors"
                                onClick={() => void remove(entry)}
                              >
                                删除
                              </button>
                            </div>
                          </td>
                        </>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        <div className="border-border text-muted-foreground flex flex-wrap items-center gap-2 border-t px-4 py-2 text-xs">
          <span>
            共{" "}
            <b className="text-foreground tabular-nums">{entries.length}</b> 条
            · 当前筛选{" "}
            <b className="text-foreground tabular-nums">{visible.length}</b> 条
          </span>
          <span className="flex-1" />
          <span className="hidden sm:inline">
            术语变更在下一次翻译 / 重跑时生效
          </span>
          <div className="flex items-center gap-2">
            <span>每页</span>
            <Select
              value={String(pageSize)}
              onValueChange={(value) => {
                setPageSize(Number(value));
                setPage(1);
                cancelEdit();
              }}
            >
              <SelectTrigger
                size="sm"
                className="h-7 w-16 text-xs"
                aria-label="每页条数"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="10">10</SelectItem>
                <SelectItem value="20">20</SelectItem>
                <SelectItem value="50">50</SelectItem>
              </SelectContent>
            </Select>
            <Button
              variant="outline"
              size="sm"
              className="h-7 px-2 text-xs"
              disabled={page <= 1}
              onClick={() => {
                setPage((prev) => prev - 1);
                cancelEdit();
              }}
            >
              上一页
            </Button>
            <span className="text-foreground min-w-16 text-center tabular-nums">
              {page} / {pageCount}
            </span>
            <Button
              variant="outline"
              size="sm"
              className="h-7 px-2 text-xs"
              disabled={page >= pageCount}
              onClick={() => {
                setPage((prev) => prev + 1);
                cancelEdit();
              }}
            >
              下一页
            </Button>
          </div>
        </div>
      </section>

      <div className="grid shrink-0 gap-3 lg:grid-cols-2">
        <section className="bg-card border-border overflow-hidden rounded-lg border">
          <div className="border-border flex flex-wrap items-center gap-2 border-b px-4 py-3">
            <h2 className="text-foreground text-sm font-semibold">动作说明</h2>
            <span className="text-muted-foreground text-xs">
              术语轴按同一口径硬校验
            </span>
          </div>
          <div className="divide-border flex flex-col divide-y">
            {[
              {
                label: "指定译法",
                value: "译文必须出现目标译法；缺失即术语轴失败",
                pill: <Pill tone="primary">force</Pill>,
              },
              {
                label: "保留原文",
                value: "不译清单：公司名 / 品牌 / 缩写保持原文",
                pill: <Pill tone="gray">forbid</Pill>,
              },
              {
                label: "原样保留",
                value: "与保留原文同效，用于强调按原文写出",
                pill: <Pill tone="info">keep</Pill>,
              },
            ].map((item) => (
              <div
                key={item.label}
                className="flex items-center gap-3 px-4 py-2.5"
              >
                <span className="text-muted-foreground w-20 shrink-0 text-xs">
                  {item.label}
                </span>
                <span className="text-foreground/80 min-w-0 flex-1 text-[13px]">
                  {item.value}
                </span>
                {item.pill}
              </div>
            ))}
          </div>
        </section>

        <section className="bg-card border-border overflow-hidden rounded-lg border">
          <div className="border-border flex flex-wrap items-center gap-2 border-b px-4 py-3">
            <h2 className="text-foreground text-sm font-semibold">生效规则</h2>
            <span className="text-muted-foreground text-xs">
              与 worker / 机检同源
            </span>
          </div>
          <div className="divide-border flex flex-col divide-y">
            {[
              [
                "语言维度",
                "EN / FR 只作用于对应源语言任务；ANY 英法文都生效",
              ],
              [
                "注入方式",
                "每个 block 只注入命中该段文本的术语，避免全表 token 膨胀",
              ],
              [
                "领域标注",
                "仅用于组织与筛选，不改变翻译/检索行为；同词同语言目标全局唯一",
              ],
              ["变更生效", "任务开始时加载；改动对下一次翻译 / 重跑生效"],
            ].map(([label, value]) => (
              <div key={label} className="flex gap-3 px-4 py-2.5">
                <span className="text-muted-foreground w-20 shrink-0 text-xs">
                  {label}
                </span>
                <span className="text-foreground/80 min-w-0 flex-1 text-[13px]">
                  {value}
                </span>
              </div>
            ))}
          </div>
        </section>
      </div>

      <NoteBar>
        术语表是硬约束，不是提示词备注：译文中未使用指定译法或改写了保留原文词，会直接进入待复核队列。批量维护请优先使用
        Excel 导入（合并模式），日常修正在表格内直接编辑。
      </NoteBar>

      {/* ═══ Excel 导入预览 ═══ */}
      <Dialog open={importOpen} onOpenChange={setImportOpen}>
        <DialogContent className="flex max-h-[90vh] max-w-[780px] flex-col gap-0 overflow-hidden p-0 sm:max-w-[780px]">
          <DialogHeader className="border-border flex-none space-y-0.5 border-b px-5 pt-4 pr-12 pb-3 text-left">
            <DialogTitle className="flex items-center gap-2 text-base leading-snug font-semibold">
              导入术语表
              <Pill tone="primary">合并导入</Pill>
            </DialogTitle>
            <DialogDescription className="text-muted-foreground text-xs">
              支持 .xlsx / .csv · 首行表头 · 最大 2 MB
            </DialogDescription>
          </DialogHeader>

          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
            <input
              ref={fileRef}
              type="file"
              accept=".xlsx,.csv"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = "";
                void handleFile(file);
              }}
            />
            <div
              role="button"
              tabIndex={0}
              aria-label="选择 Excel 或 CSV 文件"
              onClick={() => fileRef.current?.click()}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  fileRef.current?.click();
                }
              }}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                void handleFile(e.dataTransfer.files?.[0]);
              }}
              className={cn(
                "bg-muted/20 flex cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border-[1.5px] border-dashed px-4 py-5 text-center transition-colors",
                dragOver
                  ? "border-primary bg-primary/5"
                  : "border-border hover:border-primary/60 hover:bg-primary/5",
              )}
            >
              <span className="bg-primary/10 text-primary mb-1 flex h-9 w-9 items-center justify-center rounded-lg">
                {importing ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Upload className="h-4 w-4" />
                )}
              </span>
              <span className="text-[13px] font-medium">
                {importing
                  ? "正在解析…"
                  : "拖拽 Excel 到这里，或点击选择文件"}
              </span>
              <span className="text-muted-foreground text-[11px]">
                支持 .xlsx / .csv · 首行表头 · 最大 2 MB
              </span>
            </div>

            {importFileName && (
              <div className="border-border mt-2.5 flex items-center gap-2.5 rounded-md border px-3 py-2">
                <span className="flex h-8 w-8 items-center justify-center rounded-md bg-[var(--success-50)] text-[var(--success-700)]">
                  <FileSpreadsheet className="h-4 w-4" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-mono text-xs font-semibold">
                    {importFileName}
                  </span>
                  <span className="text-muted-foreground text-[11px]">
                    {importPreview
                      ? `${importPreview.summary.total ?? 0} 行 · 已解析`
                      : "解析失败或尚未完成"}
                  </span>
                </span>
                <button
                  className="text-muted-foreground hover:bg-muted hover:text-foreground rounded px-1.5 py-0.5 text-xs"
                  onClick={() => fileRef.current?.click()}
                >
                  重新选择
                </button>
              </div>
            )}

            <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
              <span className="text-muted-foreground mr-0.5 text-[11px]">
                列契约
              </span>
              {["源词", "语言", "动作", "目标译法"].map((label) => (
                <span
                  key={label}
                  className="border-border bg-muted/30 inline-flex h-5 items-center rounded border px-1.5 text-[11px]"
                >
                  {label}
                </span>
              ))}
              <span className="border-border text-muted-foreground inline-flex h-5 items-center rounded border border-dashed px-1.5 text-[11px]">
                领域（可选）
              </span>
              <span className="border-border text-muted-foreground inline-flex h-5 items-center rounded border border-dashed px-1.5 text-[11px]">
                说明（可选）
              </span>
              <span className="flex-1" />
              <span className="text-muted-foreground text-[11px]">
                动作支持 指定译法 / 保留原文 / 原样保留
              </span>
            </div>

            {importError && (
              <div
                role="alert"
                className="border-destructive/30 bg-destructive/5 text-destructive mt-2.5 flex items-start gap-2 rounded-md border px-3 py-2 text-xs"
              >
                <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>{importError}</span>
              </div>
            )}

            {importPreview && (
              <>
                {invalidCount > 0 && (
                  <div
                    role="alert"
                    className="mt-2.5 rounded-md border border-[var(--error-100)] bg-[var(--error-50)] px-3 py-2 text-xs text-[var(--error-900)]"
                  >
                    <div className="mb-1 flex items-center gap-1.5 font-semibold">
                      <TriangleAlert className="h-3.5 w-3.5" />
                      有 {invalidCount} 行未通过校验，请修正后重新上传
                    </div>
                    <ul className="ml-4 list-disc">
                      {importPreview.rows
                        .filter((row) => row.status === "invalid")
                        .map((row) => (
                          <li key={row.row}>
                            第 {row.row} 行：{row.errors.join("；")}
                          </li>
                        ))}
                    </ul>
                  </div>
                )}

                <div className="border-border mt-3 grid grid-flow-col auto-cols-fr overflow-hidden rounded-md border">
                  {(
                    [
                      ["新增", importPreview.summary.add ?? 0, "text-primary"],
                      ["更新", importPreview.summary.update ?? 0, "text-[var(--warning-900)]"],
                      ["无变化", importPreview.summary.unchanged ?? 0, "text-foreground"],
                      ["错误", importPreview.summary.invalid ?? 0, "text-destructive"],
                      ["合计", importPreview.summary.total ?? 0, "text-foreground"],
                    ] as const
                  ).map(([label, value, tone]) => (
                    <div
                      key={label}
                      className="border-border flex flex-col gap-0.5 px-3 py-2 [&:not(:first-child)]:border-l"
                    >
                      <span className="text-muted-foreground text-[11px]">
                        {label}
                      </span>
                      <span
                        className={cn(
                          "text-[17px] leading-tight font-bold tabular-nums",
                          tone,
                        )}
                      >
                        {value}
                      </span>
                    </div>
                  ))}
                </div>

                <div className="border-border mt-2.5 overflow-x-auto rounded-md border">
                  <table className="w-full border-collapse text-left">
                    <thead>
                      <tr className="bg-muted/50 border-b">
                        <th className="text-muted-foreground w-12 px-2.5 py-2 text-xs font-medium">
                          行
                        </th>
                        <th className="text-muted-foreground px-2.5 py-2 text-xs font-medium">
                          源词
                        </th>
                        <th className="text-muted-foreground w-16 px-2.5 py-2 text-xs font-medium">
                          语言
                        </th>
                        <th className="text-muted-foreground w-24 px-2.5 py-2 text-xs font-medium">
                          动作
                        </th>
                        <th className="text-muted-foreground px-2.5 py-2 text-xs font-medium">
                          目标译法
                        </th>
                        <th className="text-muted-foreground w-28 px-2.5 py-2 text-xs font-medium">
                          领域
                        </th>
                        <th className="text-muted-foreground w-32 px-2.5 py-2 text-xs font-medium">
                          说明
                        </th>
                        <th className="text-muted-foreground w-20 px-2.5 py-2 text-xs font-medium">
                          状态
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {importPreview.rows.map((row) => {
                        const oldTarget =
                          row.status === "update" ? oldTargetOf(row) : null;
                        return (
                          <tr
                            key={row.row}
                            className={cn(
                              "border-b border-[var(--gray-100)] last:border-b-0",
                              row.status === "invalid" && "bg-[var(--error-50)]",
                            )}
                          >
                            <td className="text-muted-foreground px-2.5 py-1.5 font-mono text-[11px] tabular-nums">
                              {row.row}
                            </td>
                            <td className="px-2.5 py-1.5 font-mono text-xs">
                              {row.source || "—"}
                            </td>
                            <td className="px-2.5 py-1.5">
                              <LangBadge
                                lang={
                                  (["en", "fr", "any"].includes(row.lang)
                                    ? row.lang
                                    : "any") as GlossaryLang
                                }
                              />
                            </td>
                            <td className="px-2.5 py-1.5 text-xs">
                              {ACTION_OPTIONS.find(
                                (option) => option.value === row.action,
                              )?.label ?? "—"}
                            </td>
                            <td className="px-2.5 py-1.5 text-xs">
                              {row.status === "invalid" ? (
                                <span className="text-destructive">
                                  {row.errors.join("；")}
                                </span>
                              ) : (
                                <>
                                  {oldTarget && (
                                    <span className="text-muted-foreground mr-1 line-through">
                                      {oldTarget}
                                    </span>
                                  )}
                                  {row.target ?? "—"}
                                </>
                              )}
                            </td>
                            <td className="px-2.5 py-1.5 text-xs text-muted-foreground">
                              {row.domains.length > 0
                                ? row.domains.join("、")
                                : "—"}
                            </td>
                            <td className="px-2.5 py-1.5 text-xs text-muted-foreground">
                              {row.notes ? (
                                <span
                                  className="line-clamp-1"
                                  title={row.notes}
                                >
                                  {row.notes}
                                </span>
                              ) : (
                                "—"
                              )}
                            </td>
                            <td className="px-2.5 py-1.5">
                              <ImportStatusPill status={row.status} />
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>

          <DialogFooter className="border-border bg-muted/30 flex-none flex-row items-center gap-2 border-t px-5 py-3">
            <span className="text-muted-foreground mr-auto text-[11px]">
              合并模式：按（源词, 语言）upsert；文件中未出现的存量条目保留。
            </span>
            <Button
              variant="outline"
              size="sm"
              className="text-[13px]"
              onClick={() => setImportOpen(false)}
            >
              取消
            </Button>
            <Button
              size="sm"
              className="text-[13px]"
              disabled={saving || !importPreview || invalidCount > 0}
              onClick={() => void confirmImport()}
            >
              {saving ? (
                <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
              ) : null}
              确认导入
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ═══ 新增术语 ═══ */}
      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent className="max-w-[560px] gap-0 p-0 sm:max-w-[560px]">
          <DialogHeader className="border-border space-y-0.5 border-b px-5 pt-4 pr-12 pb-3 text-left">
            <DialogTitle className="text-base leading-snug font-semibold">
              新增术语
            </DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-3 px-5 py-4">
            <div className="flex flex-col gap-1">
              <label className="text-muted-foreground text-xs font-medium">
                源词<span className="text-destructive ml-0.5">*</span>
              </label>
              <Input
                className="h-8 font-mono text-[13px]"
                value={addDraft.source}
                placeholder="例如：iron ore concentrate"
                onChange={(e) =>
                  setAddDraft({ ...addDraft, source: e.target.value })
                }
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1">
                <label className="text-muted-foreground text-xs font-medium">
                  语言
                </label>
                <Select
                  value={addDraft.lang}
                  onValueChange={(v) =>
                    setAddDraft({ ...addDraft, lang: v as GlossaryLang })
                  }
                >
                  <SelectTrigger size="sm" className="w-full text-[13px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {LANG_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-muted-foreground text-xs font-medium">
                  动作
                </label>
                <Select
                  value={addDraft.action}
                  onValueChange={(v) => {
                    const action = v as GlossaryAction;
                    setAddDraft({
                      ...addDraft,
                      action,
                      target: action === "force" ? addDraft.target : null,
                    });
                  }}
                >
                  <SelectTrigger size="sm" className="w-full text-[13px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {ACTION_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            {addDraft.action === "force" && (
              <div className="flex flex-col gap-1">
                <label className="text-muted-foreground text-xs font-medium">
                  目标译法<span className="text-destructive ml-0.5">*</span>
                </label>
                <Input
                  className="h-8 text-[13px]"
                  value={addDraft.target ?? ""}
                  placeholder="例如：铁精矿"
                  onChange={(e) =>
                    setAddDraft({ ...addDraft, target: e.target.value || null })
                  }
                />
              </div>
            )}
            <div className="flex flex-col gap-1">
              <label className="text-muted-foreground text-xs font-medium">
                领域（可选）
              </label>
              <TagInput
                value={addDraft.domains}
                onChange={(domains) =>
                  setAddDraft({ ...addDraft, domains })
                }
                placeholder="输入后回车生成标签"
                ariaLabel="业务领域标签"
              />
              <span className="text-muted-foreground text-[11px]">
                可多个；仅用于组织与筛选，不改变术语的生效范围。
              </span>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-muted-foreground text-xs font-medium">
                说明（可选）
              </label>
              <Input
                className="h-8 text-[13px]"
                value={addDraft.notes ?? ""}
                placeholder="例如：首批术语 / 旧译法待替换"
                onChange={(e) =>
                  setAddDraft({ ...addDraft, notes: e.target.value || null })
                }
              />
            </div>
          </div>
          <DialogFooter className="border-border bg-muted/30 flex-row items-center gap-2 border-t px-5 py-3">
            <span className="text-muted-foreground mr-auto text-[11px]">
              同一（源词, 语言）只允许一个目标译法
            </span>
            <Button
              variant="outline"
              size="sm"
              className="text-[13px]"
              onClick={() => setAddOpen(false)}
            >
              取消
            </Button>
            <Button
              size="sm"
              className="text-[13px]"
              disabled={saving}
              onClick={() => void saveAdd()}
            >
              保存术语
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
