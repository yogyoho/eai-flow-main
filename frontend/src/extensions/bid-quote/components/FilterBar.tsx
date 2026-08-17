"use client";

import { ChevronDown, Filter, Search } from "lucide-react";
import {
  type RefObject,
  useEffect,
  useRef,
  useState,
} from "react";

import { BLUE } from "@/extensions/bid-quote/components/chartTheme";
import {
  useFilterOptions,
  useProjectOptions,
} from "@/extensions/bid-quote/hooks";
import type { FilterState } from "@/extensions/bid-quote/types";

interface FilterBarProps {
  filters: FilterState;
  onChange: (f: FilterState) => void;
}

/** 触发按钮/面板统一样式(手写控件,14px;不依赖 shadcn Popover/Select)。 */
const TRIGGER =
  "border-border bg-background text-foreground flex w-full items-center justify-between gap-2 rounded-md border px-2.5 py-1.5 text-[14px] transition-colors hover:border-foreground/30";
const PANEL =
  "border-border bg-background absolute top-full left-0 z-30 mt-1 rounded-md border p-2 shadow-lg";

/** 点外面/ESC 关闭(三个手写下拉共用)。 */
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

/** 250ms 防抖(项目搜索防抖后进 queryKey)。 */
function useDebounced(v: string, ms = 250) {
  const [d, setD] = useState(v);
  useEffect(() => {
    const t = setTimeout(() => setD(v), ms);
    return () => clearTimeout(t);
  }, [v, ms]);
  return d;
}

/** 项目单选下拉:懒加载(首次打开才查)+ 服务端搜索(ILIKE)。FilterState.projects 仍是 string[](单选即 0/1 元素)。 */
function ProjectDropdown({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [kw, setKw] = useState("");
  const kwD = useDebounced(kw); // 250ms 防抖后进 queryKey,避免逐键打接口
  const q = useProjectOptions(open ? kwD.trim() : "", open);
  useDismiss(rootRef, open, () => setOpen(false));
  const pick = (v: string) => {
    onChange(v);
    setOpen(false);
  };
  return (
    <div className="relative" ref={rootRef}>
      <button type="button" className={TRIGGER} onClick={() => setOpen((o) => !o)} aria-label="项目">
        <span className="truncate">{value || "全部项目"}</span>
        <ChevronDown className="text-muted-foreground h-4 w-4 shrink-0" />
      </button>
      {open && (
        <div className={`${PANEL} w-80 max-w-[calc(100vw-3rem)]`}>
          <div className="relative mb-1.5">
            <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-2 h-3.5 w-3.5 -translate-y-1/2" />
            <input
              autoFocus
              value={kw}
              onChange={(e) => setKw(e.target.value)}
              placeholder="搜索项目名…"
              className="border-border bg-background placeholder:text-muted-foreground/60 w-full rounded border py-1 pr-2 pl-7 text-[14px] outline-none focus:border-foreground/40"
            />
          </div>
          <div className="max-h-60 overflow-auto">
            <button
              type="button"
              onClick={() => pick("")}
              className={`hover:bg-accent w-full cursor-pointer rounded px-2 py-1.5 text-left text-[14px] ${!value ? "text-primary font-medium" : "text-foreground"}`}
            >
              全部项目
            </button>
            {q.isPending && <div className="text-muted-foreground/60 px-2 py-1.5 text-[14px]">加载中…</div>}
            {q.isError && <div className="text-destructive/80 px-2 py-1.5 text-[14px]">加载失败</div>}
            {q.data?.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => pick(p)}
                title={p}
                className={`hover:bg-accent w-full cursor-pointer truncate rounded px-2 py-1.5 text-left text-[14px] ${p === value ? "text-primary font-medium" : "text-foreground"}`}
              >
                {p}
              </button>
            ))}
            {q.data?.length === 50 && (
              <div className="text-muted-foreground/60 px-2 py-1.5 text-[13px]">
                仅显示前 50 条,输入关键字缩小范围
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/** 友商多选下拉:复选框列表(选项来自共享 useFilterOptions,与页面其他消费方同 queryKey 去重复用)。 */
function CompetitorDropdown({
  options,
  selected,
  onToggle,
  onClear,
  status,
}: {
  options: string[];
  selected: string[];
  onToggle: (v: string) => void;
  // 清空必须单次 onChange:forEach(onToggle) 两次都基于同一份过期 filters 计算,后一次覆盖前一次只清掉一家
  onClear: () => void;
  status: "pending" | "error" | "ok";
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  useDismiss(rootRef, open, () => setOpen(false));
  return (
    <div className="relative" ref={rootRef}>
      <button type="button" className={TRIGGER} onClick={() => setOpen((o) => !o)} aria-label="友商">
        <span className="truncate">
          {selected.length === 0
            ? "全部"
            : selected.length === 1
              ? selected[0]
              : `已选 ${selected.length} 项`}
        </span>
        <ChevronDown className="text-muted-foreground h-4 w-4 shrink-0" />
      </button>
      {open && (
        <div className={`${PANEL} w-64 max-w-[calc(100vw-3rem)]`}>
          <div className="max-h-60 overflow-auto">
            {status === "pending" && options.length === 0 && (
              <div className="text-muted-foreground/60 px-2 py-1.5 text-[14px]">加载中…</div>
            )}
            {status === "error" && options.length === 0 && (
              <div className="text-destructive/80 px-2 py-1.5 text-[14px]">选项加载失败</div>
            )}
            {options.map((o) => (
              <label
                key={o}
                className="hover:bg-accent flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-[14px]"
              >
                <input
                  type="checkbox"
                  checked={selected.includes(o)}
                  onChange={() => onToggle(o)}
                  className="h-3.5 w-3.5 shrink-0"
                  style={{ accentColor: BLUE }}
                />
                <span className="truncate">{o}</span>
              </label>
            ))}
          </div>
          {selected.length > 0 && (
            <button
              type="button"
              onClick={onClear}
              className="text-muted-foreground hover:text-foreground w-full cursor-pointer px-2 py-1 text-left text-[13px]"
            >
              清空选择
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/** ISO yyyy-mm-dd(本地时区,日历格与 FilterState 同格式)。 */
function ymd(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
const WEEK = ["一", "二", "三", "四", "五", "六", "日"];

/** 日期范围选择器:自绘月历(非原生 input[type=date]),点起点→点终点成区间,悬停预览。 */
function DateRangePicker({
  from,
  to,
  onChange,
}: {
  from: string | null;
  to: string | null;
  onChange: (r: { from: string | null; to: string | null }) => void;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [view, setView] = useState(() => new Date());
  // 交互中间态:已点起点待终点;null = 展示已提交区间
  const [draft, setDraft] = useState<string | null>(null);
  const [hover, setHover] = useState<string | null>(null);
  useDismiss(rootRef, open, () => {
    setOpen(false);
    setDraft(null);
  });

  const y = view.getFullYear();
  const m = view.getMonth();
  const lead = (new Date(y, m, 1).getDay() + 6) % 7; // 周一起始的前置空格
  const daysInMonth = new Date(y, m + 1, 0).getDate();

  // 高亮区间:交互中以 draft→hover 预览,否则显示已提交 from~to
  const effFrom = draft ?? from;
  const effTo = draft ? ((hover ?? "") > draft ? hover : null) : to;

  const clickDay = (day: string) => {
    if (draft === null || day < draft) {
      setDraft(day); // 首点起点 / 点到更早日期则重定起点
      return;
    }
    onChange({ from: draft, to: day });
    setDraft(null);
    setOpen(false);
  };

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        className={TRIGGER}
        aria-label="投标日期范围"
        onClick={() => {
          // 每次打开锚定到已选起点所在月(无选择则当前月)
          setView(from ? new Date(`${from}T00:00:00`) : new Date());
          setOpen((o) => !o);
        }}
      >
        <span className="truncate">
          {from && to ? `${from} ~ ${to}` : from ? `${from} ~ …` : "全部日期"}
        </span>
        <ChevronDown className="text-muted-foreground h-4 w-4 shrink-0" />
      </button>
      {open && (
        <div className={`${PANEL} w-[19rem]`}>
          <div className="mb-1 flex items-center justify-between px-1">
            <button
              type="button"
              className="text-muted-foreground hover:text-foreground cursor-pointer rounded px-1.5 text-[14px]"
              onClick={() => setView(new Date(y, m - 1, 1))}
              aria-label="上个月"
            >
              ‹
            </button>
            <span className="text-foreground text-[14px] font-medium">
              {y}年{m + 1}月
            </span>
            <button
              type="button"
              className="text-muted-foreground hover:text-foreground cursor-pointer rounded px-1.5 text-[14px]"
              onClick={() => setView(new Date(y, m + 1, 1))}
              aria-label="下个月"
            >
              ›
            </button>
          </div>
          <div className="grid grid-cols-7">
            {WEEK.map((w) => (
              <span key={w} className="text-muted-foreground grid h-8 place-items-center text-[13px]">
                {w}
              </span>
            ))}
            {Array.from({ length: lead }, (_, i) => (
              <span key={`blank-${i}`} />
            ))}
            {Array.from({ length: daysInMonth }, (_, i) => {
              const day = ymd(new Date(y, m, i + 1));
              const isEnd = day === effFrom || day === effTo;
              const inRange = !!(effFrom && effTo && day >= effFrom && day <= effTo);
              return (
                <button
                  key={day}
                  type="button"
                  onClick={() => clickDay(day)}
                  onMouseEnter={() => setHover(day)}
                  className={`h-8 cursor-pointer rounded-md text-center text-[14px] leading-8 ${
                    isEnd
                      ? "text-white"
                      : inRange
                        ? "bg-accent text-foreground"
                        : "hover:bg-accent text-foreground"
                  }`}
                  style={isEnd ? { background: BLUE } : undefined}
                >
                  {i + 1}
                </button>
              );
            })}
          </div>
          <div className="mt-1 flex items-center justify-between px-1">
            <span className="text-muted-foreground/70 text-[13px]">点击两下选起止区间</span>
            {(from !== null || to !== null) && (
              <button
                type="button"
                className="text-muted-foreground hover:text-foreground cursor-pointer text-[13px]"
                onClick={() => {
                  onChange({ from: null, to: null });
                  setOpen(false);
                }}
              >
                清空日期
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export function FilterBar({ filters, onChange }: FilterBarProps) {
  const optsQ = useFilterOptions();
  const opts = optsQ.data ?? { projects: [], competitors: [], goods: [] };
  // 用查询状态而非 options.length 区分 加载中/失败,避免请求失败时永远显示"加载中…"
  const status = optsQ.isPending ? "pending" : optsQ.isError ? "error" : "ok";
  const toggle = (key: "projects" | "competitors", v: string) => {
    const cur = filters[key];
    onChange({
      ...filters,
      [key]: cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v],
    });
  };
  const active =
    !!filters.dateFrom ||
    !!filters.dateTo ||
    filters.projects.length > 0 ||
    filters.competitors.length > 0;

  return (
    <div className="border-border bg-card/50 rounded-xl border p-3">
      <div className="text-muted-foreground mb-2 flex items-center gap-2 text-[14px] font-medium">
        <Filter className="h-4 w-4" />
        全局过滤(所有图表联动)
        {active && (
          <button
            type="button"
            onClick={() =>
              onChange({
                projects: [],
                competitors: [],
                dateFrom: null,
                dateTo: null,
              })
            }
            className="text-primary ml-auto cursor-pointer text-[14px] hover:underline"
          >
            清空
          </button>
        )}
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <div className="flex flex-col gap-1" role="group" aria-label="项目">
          <span className="text-muted-foreground text-[12px]">项目</span>
          <ProjectDropdown
            value={filters.projects[0] ?? ""}
            onChange={(v) => onChange({ ...filters, projects: v ? [v] : [] })}
          />
        </div>
        <div className="flex flex-col gap-1" role="group" aria-label="友商">
          <span className="text-muted-foreground text-[12px]">友商</span>
          <CompetitorDropdown
            options={opts.competitors}
            selected={filters.competitors}
            onToggle={(v) => toggle("competitors", v)}
            onClear={() => onChange({ ...filters, competitors: [] })}
            status={status}
          />
        </div>
        <div className="flex flex-col gap-1" role="group" aria-label="投标日期">
          <span className="text-muted-foreground text-[12px]">投标日期</span>
          <DateRangePicker
            from={filters.dateFrom}
            to={filters.dateTo}
            onChange={(r) => onChange({ ...filters, dateFrom: r.from, dateTo: r.to })}
          />
        </div>
      </div>
    </div>
  );
}
