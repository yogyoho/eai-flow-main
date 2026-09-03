"use client";

// EAI-CUSTOM: geo-sample-bank Phase 1 FilterBar — bid-quote FilterBar 风格
// (手写触发器/面板下拉,不依赖 shadcn Popover/Select)。选项为静态客户端枚举
// (阶段/矿种/状态),无服务端搜索,故未搬 bid-quote 的 useDebounced/useProjectOptions。
import { ChevronDown, Filter } from "lucide-react";
import { type RefObject, useEffect, useRef, useState } from "react";

/** 样例文档列表筛选状态(空串 = 不过滤)。 */
export interface GsbDocFilters {
  stage: string;
  mineral: string;
  status: string;
}

export interface GsbOption {
  value: string;
  label: string;
}

export const STAGE_OPTIONS: GsbOption[] = [
  { value: "survey", label: "普查" },
  { value: "detail", label: "详查" },
  { value: "exploration", label: "勘探" },
];

export const MINERAL_OPTIONS: GsbOption[] = [
  { value: "copper", label: "铜" },
  { value: "coal", label: "煤" },
  { value: "gold", label: "金" },
  { value: "iron", label: "铁" },
  { value: "lead_zinc", label: "铅锌" },
  { value: "other", label: "其他" },
];

export const STATUS_OPTIONS: GsbOption[] = [
  { value: "uploaded", label: "已上传" },
  { value: "parsed", label: "已解析" },
  { value: "redacted", label: "已脱敏" },
  { value: "reviewed", label: "已过审" },
  { value: "failed", label: "失败" },
  { value: "compiled", label: "已编译" },
];

/** 触发按钮/面板统一样式(bid-quote FilterBar 同款,14px)。 */
const TRIGGER =
  "border-border bg-background text-foreground flex w-full items-center justify-between gap-2 rounded-md border px-2.5 py-1.5 text-[14px] transition-colors hover:border-foreground/30";
const PANEL =
  "border-border bg-background absolute top-full left-0 z-30 mt-1 rounded-md border p-2 shadow-lg";

/** 点外面/ESC 关闭(bid-quote FilterBar 同款)。 */
function useDismiss(
  ref: RefObject<HTMLDivElement | null>,
  open: boolean,
  close: () => void,
) {
  useEffect(() => {
    if (!open) return;
    const onDown = (e: Event) => {
      if (ref.current && !ref.current.contains(e.target as Node)) close();
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [ref, open, close]);
}

/** 通用单选下拉(静态选项;value 为空串时显示 allLabel 复位项)。 */
export function SelectDropdown({
  ariaLabel,
  value,
  allLabel,
  options,
  onChange,
}: {
  ariaLabel: string;
  value: string;
  /** 复位项文案(如「全部阶段」/「选择待审样例(N)」)。 */
  allLabel: string;
  options: GsbOption[];
  onChange: (v: string) => void;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  useDismiss(rootRef, open, () => setOpen(false));
  const current = options.find((o) => o.value === value)?.label;
  const pick = (v: string) => {
    onChange(v);
    setOpen(false);
  };
  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        className={TRIGGER}
        onClick={() => setOpen((o) => !o)}
        aria-label={ariaLabel}
      >
        <span className="truncate">
          {value ? (current ?? value) : allLabel}
        </span>
        <ChevronDown className="text-muted-foreground h-4 w-4 shrink-0" />
      </button>
      {open && (
        <div className={`${PANEL} w-64 max-w-[calc(100vw-3rem)]`}>
          <div className="max-h-60 overflow-auto">
            <button
              type="button"
              onClick={() => pick("")}
              className={`hover:bg-accent w-full cursor-pointer rounded px-2 py-1.5 text-left text-[14px] ${!value ? "text-primary font-medium" : "text-foreground"}`}
            >
              {allLabel}
            </button>
            {options.map((o) => (
              <button
                key={o.value}
                type="button"
                onClick={() => pick(o.value)}
                title={o.label}
                className={`hover:bg-accent w-full cursor-pointer truncate rounded px-2 py-1.5 text-left text-[14px] ${o.value === value ? "text-primary font-medium" : "text-foreground"}`}
              >
                {o.label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/** 样例文档筛选条:阶段/矿种/状态三下拉(bid-quote FilterBar 布局同款)。 */
export function FilterBar({
  filters,
  onChange,
}: {
  filters: GsbDocFilters;
  onChange: (f: GsbDocFilters) => void;
}) {
  const active = !!filters.stage || !!filters.mineral || !!filters.status;

  return (
    <div className="border-border bg-card/50 rounded-xl border p-3">
      <div className="text-muted-foreground mb-2 flex items-center gap-2 text-[14px] font-medium">
        <Filter className="h-4 w-4" />
        筛选样例
        {active && (
          <button
            type="button"
            onClick={() => onChange({ stage: "", mineral: "", status: "" })}
            className="text-primary ml-auto cursor-pointer text-[14px] hover:underline"
          >
            清空
          </button>
        )}
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <div className="flex flex-col gap-1" role="group" aria-label="勘查阶段">
          <span className="text-muted-foreground text-[12px]">勘查阶段</span>
          <SelectDropdown
            ariaLabel="勘查阶段"
            value={filters.stage}
            allLabel="全部阶段"
            options={STAGE_OPTIONS}
            onChange={(v) => onChange({ ...filters, stage: v })}
          />
        </div>
        <div className="flex flex-col gap-1" role="group" aria-label="矿种">
          <span className="text-muted-foreground text-[12px]">矿种</span>
          <SelectDropdown
            ariaLabel="矿种"
            value={filters.mineral}
            allLabel="全部矿种"
            options={MINERAL_OPTIONS}
            onChange={(v) => onChange({ ...filters, mineral: v })}
          />
        </div>
        <div className="flex flex-col gap-1" role="group" aria-label="状态">
          <span className="text-muted-foreground text-[12px]">状态</span>
          <SelectDropdown
            ariaLabel="状态"
            value={filters.status}
            allLabel="全部状态"
            options={STATUS_OPTIONS}
            onChange={(v) => onChange({ ...filters, status: v })}
          />
        </div>
      </div>
    </div>
  );
}
