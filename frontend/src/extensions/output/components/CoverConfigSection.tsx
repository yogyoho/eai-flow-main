"use client";

import {
  Check,
  FileText,
  FileUp,
  Image as ImageIcon,
  Trash2,
  Type,
} from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { AdminSelect } from "@/components/ui/admin-select";
import {
  COVER_EMPTY_ELEMENTS,
  coverLogoPosition,
  coverSlotEffectiveKind,
  coverSlotSourceLabel,
  isCoverSlotResolvable,
  patchCoverState,
  resolveCoverFromImport,
  syncSlotTarget,
} from "@/extensions/output/cover-state";
import type {
  Cover,
  CoverMaster,
  CoverSlot,
  CoverTemplate,
} from "@/extensions/output/types";
import { cn } from "@/lib/utils";

import { CoverElementsEditor } from "./CoverElementsEditor";

// ─────────────────────────────────────────────────────────────────────────────
// Primitives (kept local — shared by the three cover modes only)
// ─────────────────────────────────────────────────────────────────────────────

function Toggle({
  checked,
  onChange,
  label,
  icon: Icon,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  icon?: React.ComponentType<{ className?: string }>;
}) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={cn(
        "flex w-full items-center gap-2.5 rounded-lg border px-3 py-2 text-left text-sm transition-all",
        checked
          ? "border-primary/30 bg-primary/5 text-foreground"
          : "border-border bg-background text-muted-foreground hover:border-input hover:bg-muted/40",
      )}
    >
      <span
        className={cn(
          "flex h-4 w-4 shrink-0 items-center justify-center rounded-[5px] border transition-all",
          checked
            ? "border-primary bg-primary text-primary-foreground"
            : "border-input bg-background",
        )}
      >
        {checked && <Check className="h-3 w-3" strokeWidth={3} />}
      </span>
      {Icon && (
        <Icon
          className={cn(
            "h-3.5 w-3.5",
            checked ? "text-primary" : "text-muted-foreground/70",
          )}
        />
      )}
      <span className="flex-1">{label}</span>
    </button>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <label className="text-muted-foreground text-[11px] font-medium">
          {label}
        </label>
        {hint && (
          <span className="text-muted-foreground/60 shrink-0 text-[10px] font-normal">
            {hint}
          </span>
        )}
      </div>
      {children}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// CoverConfigSection
// ─────────────────────────────────────────────────────────────────────────────

export interface CoverState {
  template: CoverTemplate | null;
  master: CoverMaster | null;
  elements: Cover | null;
}

interface CoverConfigSectionProps {
  /** Current cover state (controlled). */
  value: CoverState;
  /** Emit a new cover state. */
  onChange: (next: CoverState) => void;
}

/**
 * 封面配置（EAI-CUSTOM，排版模版编辑器与导出对话框共用，保证功能对齐）。
 *
 * 三种互斥模式，优先级 elements > master > template（5 开关）：
 * - elements：结构化封面（CoverElementsEditor）
 * - master：从样例 .docx 导入的槽位母版
 * - template：5 开关 + logo 位置 + 预览
 * 封面值仅在生成时从内容 frontmatter 解析，此处不编辑值本身。
 */
export function CoverConfigSection({
  value,
  onChange,
}: CoverConfigSectionProps) {
  const { template, master, elements } = value;
  const [importing, setImporting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const patchTemplate = (p: Partial<CoverTemplate>) =>
    onChange({ ...value, template: patchCoverState(template, p) });

  const patchSlot = (index: number, p: Partial<CoverSlot>) =>
    onChange({
      ...value,
      master: master
        ? {
            ...master,
            slots: master.slots.map((s, i) =>
              i === index ? { ...s, ...p } : s,
            ),
          }
        : master,
    });

  const clearAll = () =>
    onChange({ template: null, master: null, elements: null });

  const handleImportClick = () => fileInputRef.current?.click();

  const handleImportedFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    try {
      const { outputApi } = await import("@/extensions/output/api");
      const data = await outputApi.importLayout(file);
      const { coverMaster, coverTemplate } = resolveCoverFromImport(data);
      const ce = data.cover_elements as Cover | null | undefined;
      onChange({
        elements: ce?.mode === "elements" ? ce : null,
        master: coverMaster,
        // undefined = "保持当前 5 开关兜底休眠"，与 LayoutTemplateEditor.applyCoverImport 语义一致
        template: coverTemplate !== undefined ? coverTemplate : value.template,
      });
      toast.success("已从样例导入封面");
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "无法从该文件提取排版信息",
      );
    } finally {
      setImporting(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  return (
    <div className="space-y-3">
      {elements ? (
        <>
          <div className="bg-muted/40 flex items-center gap-2 rounded-lg px-3 py-2 text-xs">
            <FileText className="text-muted-foreground h-3.5 w-3.5 shrink-0" />
            <span className="text-muted-foreground truncate">
              来自样例：{elements.sourceFile ?? "（未命名）"}
            </span>
            <button
              type="button"
              onClick={clearAll}
              className="border-border text-destructive hover:bg-destructive/10 ml-auto shrink-0 rounded-md border px-2 py-0.5 text-[10px] font-medium"
            >
              移除封面
            </button>
          </div>
          <CoverElementsEditor
            cover={elements}
            onChange={(c) => onChange({ ...value, elements: c })}
          />
        </>
      ) : master ? (
        <>
          <div className="bg-muted/40 flex items-center gap-2 rounded-lg px-3 py-2 text-xs">
            <FileText className="text-muted-foreground h-3.5 w-3.5 shrink-0" />
            <span className="text-muted-foreground truncate">
              来自样例：
              <span className="text-foreground font-medium">
                {master.sourceFile || "（未命名）"}
              </span>
            </span>
            <span className="bg-primary/10 text-primary ml-auto shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium">
              {master.boundary === "before_toc" ? "目录前" : "首标题前"}
            </span>
          </div>
          <div className="space-y-1.5">
            <p className="text-muted-foreground text-[11px] font-medium">
              {`槽位（生成时替换"变量"，保留"字面"）`}
            </p>
            <p className="text-muted-foreground/70 text-[10px]">
              原文靶文本：生成时按此文本（带标签字段按「标签+原文」整体）定位并替换；须与封面原文匹配才生效。
            </p>
            {master.slots.map((slot, i) => {
              const resolvable = isCoverSlotResolvable(slot.id);
              const kind = coverSlotEffectiveKind(slot);
              return (
                <div
                  key={slot.id}
                  className="border-border flex items-center gap-2 rounded-lg border px-2 py-1.5"
                >
                  <span className="text-muted-foreground flex w-32 shrink-0 flex-col">
                    <span className="text-[11px] font-medium">
                      {slot.label}
                    </span>
                    <span
                      className="text-muted-foreground/60 truncate text-[9px]"
                      title={coverSlotSourceLabel(slot.id, slot.defaultFrom)}
                    >
                      {coverSlotSourceLabel(slot.id, slot.defaultFrom)}
                    </span>
                  </span>
                  {kind === "literal" ? (
                    <span className="border-border text-muted-foreground bg-background flex h-7 flex-1 items-center rounded-md border px-2 text-xs">
                      {slot.sampleValue}
                    </span>
                  ) : (
                    <input
                      className="border-border bg-background h-7 flex-1 rounded-md border px-2 text-xs"
                      value={slot.sampleValue}
                      onChange={(e) =>
                        patchSlot(i, {
                          sampleValue: e.target.value,
                          target: syncSlotTarget(slot, e.target.value),
                        })
                      }
                      placeholder="原文靶文本"
                      title="原文靶文本——生成时按此文本定位并替换；带标签字段以「标签+原文」定位，须与封面原文匹配才生效"
                    />
                  )}
                  <button
                    type="button"
                    disabled={!resolvable}
                    onClick={() =>
                      patchSlot(i, {
                        kind: slot.kind === "variable" ? "literal" : "variable",
                      })
                    }
                    className={`ring-border shrink-0 rounded-md px-2 py-1 text-[10px] font-medium ring-1 transition-colors ring-inset ${kind === "variable" ? "text-primary" : "text-muted-foreground"} ${resolvable ? "hover:bg-muted" : "cursor-not-allowed opacity-50"}`}
                    title={
                      resolvable
                        ? kind === "variable"
                          ? "点击切为字面（原样保留不替换）"
                          : "点击切为变量（生成时替换）"
                        : "该槽位生成时无取值来源，仅保留原文"
                    }
                  >
                    {kind === "variable" ? "变量" : "字面"}
                  </button>
                </div>
              );
            })}
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleImportClick}
              disabled={importing}
              className="border-border text-muted-foreground hover:bg-muted flex flex-1 items-center justify-center gap-2 rounded-lg border border-dashed px-3 py-2 text-xs font-medium transition-colors disabled:opacity-50"
            >
              <FileUp className="h-3.5 w-3.5" />
              {importing ? "提取中…" : "重新从样例导入封面"}
            </button>
            <button
              type="button"
              onClick={() => onChange({ ...value, master: null })}
              className="border-border text-destructive hover:bg-destructive/10 flex shrink-0 items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-medium transition-colors"
            >
              <Trash2 className="h-3.5 w-3.5" /> 移除母版
            </button>
          </div>
        </>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-2">
            <Toggle
              checked={template?.showLogo ?? false}
              onChange={(v) => patchTemplate({ showLogo: v })}
              label="显示 Logo"
              icon={ImageIcon}
            />
            <Toggle
              checked={template?.showTitle ?? false}
              onChange={(v) => patchTemplate({ showTitle: v })}
              label="显示标题"
              icon={Type}
            />
            <Toggle
              checked={template?.showClient ?? false}
              onChange={(v) => patchTemplate({ showClient: v })}
              label="显示建设单位"
            />
            <Toggle
              checked={template?.showDate ?? false}
              onChange={(v) => patchTemplate({ showDate: v })}
              label="显示日期"
            />
            <Toggle
              checked={template?.showProjectNumber ?? false}
              onChange={(v) => patchTemplate({ showProjectNumber: v })}
              label="显示项目编号"
            />
          </div>
          {template?.showLogo && (
            <Field label="Logo 位置">
              <AdminSelect
                value={coverLogoPosition(template)}
                onChange={(v) =>
                  patchTemplate({
                    logoPosition: v as CoverTemplate["logoPosition"],
                  })
                }
                options={[
                  { value: "left", label: "左" },
                  { value: "center", label: "中" },
                  { value: "right", label: "右" },
                ]}
                className="w-full"
              />
            </Field>
          )}
          {((template?.showLogo ?? false) ||
            (template?.showTitle ?? false) ||
            (template?.showClient ?? false) ||
            (template?.showDate ?? false) ||
            (template?.showProjectNumber ?? false)) && (
            <div className="bg-muted/30 rounded-lg p-5">
              <p className="text-muted-foreground mb-3 text-[10px] font-semibold tracking-wide uppercase">
                预览
              </p>
              <div className="mx-auto max-w-[240px] space-y-2.5 text-center">
                {template?.showLogo && (
                  <div
                    className={cn(
                      "flex w-full",
                      template.logoPosition === "left"
                        ? "justify-start"
                        : template.logoPosition === "right"
                          ? "justify-end"
                          : "justify-center",
                    )}
                  >
                    <div className="bg-primary/10 text-primary ring-primary/15 flex h-12 w-20 items-center justify-center rounded-md text-[10px] font-medium ring-1 ring-inset">
                      LOGO
                    </div>
                  </div>
                )}
                {template?.showTitle && (
                  <div className="text-foreground text-lg font-bold">
                    报告标题
                  </div>
                )}
                <div className="text-muted-foreground space-y-1.5 pt-1 text-xs">
                  {template?.showClient && <div>建设单位：XXXX</div>}
                  {template?.showDate && <div>日期：2026-08</div>}
                  {template?.showProjectNumber && <div>项目编号：XXXX</div>}
                </div>
              </div>
            </div>
          )}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() =>
                onChange({ ...value, elements: COVER_EMPTY_ELEMENTS })
              }
              className="border-border text-muted-foreground hover:bg-muted flex flex-1 items-center justify-center gap-2 rounded-lg border border-dashed px-3 py-2 text-xs font-medium transition-colors"
            >
              <Type className="h-3.5 w-3.5" />
              用元素编辑器
            </button>
            <button
              type="button"
              onClick={handleImportClick}
              disabled={importing}
              className="border-border text-primary hover:bg-primary/5 flex flex-1 items-center justify-center gap-2 rounded-lg border border-dashed px-3 py-2 text-xs font-medium transition-colors disabled:opacity-50"
            >
              <FileUp className="h-3.5 w-3.5" />
              {importing ? "提取中…" : "从样例 .docx 导入真实封面"}
            </button>
            {template && (
              <button
                type="button"
                onClick={() => onChange({ ...value, template: null })}
                className="border-border text-destructive hover:bg-destructive/10 flex shrink-0 items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-medium transition-colors"
              >
                <Trash2 className="h-3.5 w-3.5" /> 移除封面
              </button>
            )}
          </div>
        </>
      )}

      {/* 封面专用样例导入（.docx）——与 LayoutTemplateEditor 的整表导入共用同一后端接口 */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".docx"
        className="hidden"
        onChange={handleImportedFile}
      />
    </div>
  );
}
