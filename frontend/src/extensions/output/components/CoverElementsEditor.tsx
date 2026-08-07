"use client";

import {
  AlignCenter,
  AlignLeft,
  AlignRight,
  ArrowDown,
  ArrowUp,
  Bold,
  GripVertical,
  Image as ImageIcon,
  Minus,
  Plus,
  Trash2,
  X,
} from "lucide-react";
import { Fragment, useCallback, useState } from "react";

import { AdminSelect } from "@/components/ui/admin-select";
import {
  COVER_SLOT_OPTIONS,
  patchCoverElementsPage,
} from "@/extensions/output/cover-state";
import type {
  Cover,
  CoverElement,
  CoverElementType,
} from "@/extensions/output/types";
import { cn } from "@/lib/utils";

// ─────────────────────────────────────────────────────────────────────────────
// 元素元信息与创建
// ─────────────────────────────────────────────────────────────────────────────

/** AdminSelect 的"不绑定"哨兵值 —— Radix Select 禁止空串作为 option value
 * （@radix-ui/react-select@2.2.6 在 SelectItem value === "" 时直接 throw），
 * 因此用项目惯例的 `__none__` 哨兵占位，onChange 时再映射回 null。 */
const UNBOUND = "__none__";

/** 每种元素类型的展示名 + 类型徽标配色。 */
const ELEMENT_TYPE_META: Record<
  CoverElementType,
  { label: string; badgeCls: string }
> = {
  text: { label: "文本", badgeCls: "bg-primary/10 text-primary" },
  table: { label: "表格", badgeCls: "bg-emerald-500/10 text-emerald-600" },
  image: { label: "Logo", badgeCls: "bg-amber-500/10 text-amber-600" },
  spacer: { label: "空行", badgeCls: "bg-muted text-muted-foreground" },
  divider: { label: "分页符", badgeCls: "bg-muted text-muted-foreground" },
};

/** 文本元素可选字体（生成时经 generator._resolve_font 映射到 python-docx 字体名）。 */
const COVER_FONT_OPTIONS: { value: string; label: string }[] = [
  { value: "宋体", label: "宋体" },
  { value: "黑体", label: "黑体" },
  { value: "仿宋", label: "仿宋" },
  { value: "楷体", label: "楷体" },
  { value: "微软雅黑", label: "微软雅黑" },
  { value: "等线", label: "等线" },
  { value: "Times New Roman", label: "Times New Roman" },
];

/** 元素自增 ID 生成器 —— 仅在一次会话内保证唯一即可（Task 2 已保证存量元素 id 唯一）。 */
let elementIdSeq = 0;
function newElementId(): string {
  elementIdSeq += 1;
  return `el-${Date.now().toString(36)}-${elementIdSeq}`;
}

/** 按类型创建带合理默认值的新元素（未持久化，由父组件 onChange 落入 state）。 */
function createElement(type: CoverElementType): CoverElement {
  const id = newElementId();
  switch (type) {
    case "text":
      return {
        id,
        type,
        text: "",
        fontSize: 12,
        bold: false,
        alignment: "center",
        slotId: null,
      };
    case "table":
      return {
        id,
        type,
        rows: 2,
        cols: 2,
        cells: [
          ["", ""],
          ["", ""],
        ],
        headerBg: null,
      };
    case "image":
      return { id, type, image: null };
    case "spacer":
      return { id, type, lines: 1 };
    case "divider":
      return { id, type };
    default:
      // 穷尽所有元素类型，避免遗漏
      throw new Error(`未知封面元素类型: ${String(type)}`);
  }
}

/** 把表格元素的 cells 规范化为 rows×cols 二维数组（防御导入/迁移带来的尺寸不一致）。 */
function tableCells(el: CoverElement): string[][] {
  const rows = el.rows ?? 0;
  const cols = el.cols ?? 0;
  return Array.from({ length: rows }, (_, r) =>
    Array.from({ length: cols }, (_, c) => el.cells?.[r]?.[c] ?? ""),
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// 样式原语
// ─────────────────────────────────────────────────────────────────────────────

const inputCls =
  "w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-xs text-foreground outline-none transition-all placeholder:text-muted-foreground/50 hover:border-primary/40 focus:border-primary focus:ring-2 focus:ring-primary/20";

const ghostBtnCls =
  "flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:cursor-not-allowed disabled:opacity-30";

const tableCellCls =
  "w-full min-w-[3rem] rounded-md border border-input bg-background px-2 py-1 text-xs text-foreground outline-none transition-all hover:border-primary/40 focus:border-primary focus:ring-2 focus:ring-primary/20";

function MiniBtn({ onClick, label }: { onClick: () => void; label: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="border-border text-muted-foreground hover:bg-muted hover:text-foreground rounded-md border px-2 py-1 text-[10px] font-medium transition-colors"
    >
      {label}
    </button>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// 各元素类型的编辑体
// ─────────────────────────────────────────────────────────────────────────────

/** 文本元素：文本 input + 绑定下拉 + 字号 + 加粗 + 对齐。 */
function TextElementBody({
  el,
  onPatch,
}: {
  el: CoverElement;
  onPatch: (patch: Partial<CoverElement>) => void;
}) {
  // 字号输入允许"清空中的瞬态"（清空时本地草稿为空串，不失焦前不强制回填 12）
  const [sizeDraft, setSizeDraft] = useState<string | null>(null);
  const sizeValue = sizeDraft ?? String(el.fontSize ?? 12);
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <input
        type="text"
        value={el.text ?? ""}
        onChange={(e) => onPatch({ text: e.target.value })}
        placeholder="文本内容"
        aria-label="文本内容"
        className={cn(inputCls, "min-w-[120px] flex-1")}
      />
      <AdminSelect
        value={el.slotId ?? UNBOUND}
        onChange={(v) => onPatch({ slotId: v === UNBOUND ? null : v })}
        options={[{ value: UNBOUND, label: "不绑定" }, ...COVER_SLOT_OPTIONS]}
        // text-xs 与左侧文本输入框（inputCls）字号对齐；twMerge 会覆盖 AdminSelect 内置 text-sm
        className="w-32 text-xs"
      />
      <input
        type="number"
        value={sizeValue}
        onChange={(e) => {
          setSizeDraft(e.target.value);
          const n = parseInt(e.target.value, 10);
          if (e.target.value !== "" && !Number.isNaN(n)) {
            onPatch({ fontSize: n });
          }
        }}
        onBlur={() => setSizeDraft(null)}
        aria-label="字号 (pt)"
        className={cn(inputCls, "w-14 px-2 text-center")}
      />
      <button
        type="button"
        onClick={() => onPatch({ bold: !el.bold })}
        className={cn(ghostBtnCls, el.bold && "bg-primary/10 text-primary")}
        aria-label="加粗"
        aria-pressed={!!el.bold}
      >
        <Bold className="h-3.5 w-3.5" />
      </button>
      <div className="flex items-center gap-0.5">
        {(
          [
            ["left", AlignLeft],
            ["center", AlignCenter],
            ["right", AlignRight],
          ] as const
        ).map(([val, Icon]) => (
          <button
            key={val}
            type="button"
            onClick={() => onPatch({ alignment: val })}
            className={cn(
              ghostBtnCls,
              (el.alignment ?? "center") === val &&
                "bg-primary/10 text-primary",
            )}
            aria-label={
              val === "left" ? "左对齐" : val === "right" ? "右对齐" : "居中"
            }
            aria-pressed={(el.alignment ?? "center") === val}
          >
            <Icon className="h-3.5 w-3.5" />
          </button>
        ))}
      </div>
      <AdminSelect
        value={el.fontFamily ?? "宋体"}
        onChange={(v) => onPatch({ fontFamily: v })}
        options={COVER_FONT_OPTIONS}
        className="w-24 text-xs"
      />
    </div>
  );
}

/** 空行元素：± 行数。 */
function SpacerBody({
  el,
  onPatch,
}: {
  el: CoverElement;
  onPatch: (patch: Partial<CoverElement>) => void;
}) {
  const lines = el.lines ?? 1;
  return (
    <div className="text-muted-foreground flex items-center gap-1.5 text-xs">
      <span>空行</span>
      <button
        type="button"
        onClick={() => onPatch({ lines: Math.max(1, lines - 1) })}
        className={cn(ghostBtnCls, "h-5 w-5")}
        aria-label="减少空行"
      >
        <Minus className="h-3 w-3" />
      </button>
      <span className="text-foreground w-4 text-center font-semibold">
        {lines}
      </span>
      <button
        type="button"
        onClick={() => onPatch({ lines: lines + 1 })}
        className={cn(ghostBtnCls, "h-5 w-5")}
        aria-label="增加空行"
      >
        <Plus className="h-3 w-3" />
      </button>
      <span className="text-muted-foreground/60">行</span>
    </div>
  );
}

/** 表格元素：行列增删 + 表头开关 + cells 网格。 */
function TableBody({
  el,
  onPatch,
  onCell,
  onResize,
}: {
  el: CoverElement;
  onPatch: (patch: Partial<CoverElement>) => void;
  onCell: (r: number, c: number, v: string) => void;
  onResize: (dr: number, dc: number) => void;
}) {
  const cols = el.cols ?? 0;
  const cells = tableCells(el);
  return (
    <div className="border-border space-y-2 border-t p-2.5">
      <div className="flex items-center gap-1">
        <MiniBtn onClick={() => onResize(1, 0)} label="+行" />
        <MiniBtn onClick={() => onResize(-1, 0)} label="-行" />
        <MiniBtn onClick={() => onResize(0, 1)} label="+列" />
        <MiniBtn onClick={() => onResize(0, -1)} label="-列" />
        <label className="text-muted-foreground ml-auto flex cursor-pointer items-center gap-1.5 text-[11px]">
          <input
            type="checkbox"
            checked={!!el.headerBg}
            onChange={(e) =>
              onPatch({ headerBg: e.target.checked ? "#2B579A" : null })
            }
            className="size-3.5"
          />
          首行为表头
        </label>
      </div>
      <div
        className="grid gap-1"
        style={{
          gridTemplateColumns: `repeat(${Math.max(cols, 1)}, minmax(0, 1fr))`,
        }}
      >
        {cells.map((row, r) =>
          row.map((cell, c) => (
            <input
              key={`${r}-${c}`}
              type="text"
              value={cell}
              onChange={(e) => onCell(r, c, e.target.value)}
              aria-label={`单元格 第 ${r + 1} 行 第 ${c + 1} 列`}
              className={cn(
                tableCellCls,
                r === 0 && el.headerBg && "font-medium",
              )}
            />
          )),
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// 元素行
// ─────────────────────────────────────────────────────────────────────────────

interface ElementRowProps {
  el: CoverElement;
  index: number;
  count: number;
  onPatch: (patch: Partial<CoverElement>) => void;
  onRemove: () => void;
  onMove: (dir: -1 | 1) => void;
  onCell: (r: number, c: number, v: string) => void;
  onResize: (dr: number, dc: number) => void;
  onDragStart: () => void;
  onDragOver: () => void;
  onDrop: () => void;
  onDragEnd: () => void;
  dragging: boolean;
  dragOver: boolean;
}

function ElementRow({
  el,
  index,
  count,
  onPatch,
  onRemove,
  onMove,
  onCell,
  onResize,
  onDragStart,
  onDragOver,
  onDrop,
  onDragEnd,
  dragging,
  dragOver,
}: ElementRowProps) {
  const meta = ELEMENT_TYPE_META[el.type];
  return (
    <div
      className={cn(
        "border-border bg-background rounded-lg border transition-shadow",
        dragOver && "ring-primary/60 ring-2 ring-inset",
        dragging && "opacity-40",
      )}
      onDragOver={(e) => {
        e.preventDefault();
        onDragOver();
      }}
      onDrop={(e) => {
        e.preventDefault();
        onDrop();
      }}
    >
      <div className="flex items-center gap-2 px-2.5 py-1.5">
        <button
          type="button"
          draggable
          onDragStart={onDragStart}
          onDragEnd={onDragEnd}
          className="text-muted-foreground/40 hover:text-muted-foreground shrink-0 cursor-grab rounded p-0.5 transition-colors active:cursor-grabbing"
          aria-label="拖动排序"
          title="拖动排序"
        >
          <GripVertical className="h-3.5 w-3.5" />
        </button>
        <span className="text-muted-foreground/50 w-4 shrink-0 text-center text-[10px]">
          {index + 1}
        </span>
        <span
          className={cn(
            "flex h-5 shrink-0 items-center rounded-md px-1.5 text-[10px] font-semibold",
            meta.badgeCls,
          )}
        >
          {meta.label}
        </span>
        <div className="min-w-0 flex-1">
          {el.type === "text" && <TextElementBody el={el} onPatch={onPatch} />}
          {el.type === "table" && (
            <span className="text-muted-foreground text-xs">
              {el.rows ?? 0}×{el.cols ?? 0} 单元格
            </span>
          )}
          {el.type === "image" && (
            <span className="text-muted-foreground flex items-center gap-1 text-xs">
              <ImageIcon className="h-3.5 w-3.5" />
              {el.image?.b64 ? "Logo 已配置（导入）" : "Logo（导入时自动填充）"}
            </span>
          )}
          {el.type === "spacer" && <SpacerBody el={el} onPatch={onPatch} />}
          {el.type === "divider" && (
            <span className="text-muted-foreground flex items-center gap-1.5 text-xs">
              <span className="border-muted-foreground/30 border-t w-6" /> 分页符
            </span>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-0.5">
          <button
            type="button"
            onClick={() => onMove(-1)}
            disabled={index === 0}
            className={ghostBtnCls}
            aria-label="上移"
          >
            <ArrowUp className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={() => onMove(1)}
            disabled={index === count - 1}
            className={ghostBtnCls}
            aria-label="下移"
          >
            <ArrowDown className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={onRemove}
            className={cn(ghostBtnCls, "hover:text-destructive")}
            aria-label="删除"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {el.type === "table" && (
        <TableBody
          el={el}
          onPatch={onPatch}
          onCell={onCell}
          onResize={onResize}
        />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// 插入位（元素间）：折叠为一条 ＋，展开为类型选择菜单，插入到指定 index
// ─────────────────────────────────────────────────────────────────────────────

function InsertZone({
  open,
  onToggle,
  onInsert,
}: {
  open: boolean;
  onToggle: () => void;
  onInsert: (t: CoverElementType) => void;
}) {
  if (!open) {
    return (
      <button
        type="button"
        onClick={onToggle}
        aria-label="在指定位置插入元素"
        title="在指定位置插入元素"
        className="group flex w-full items-center gap-1 py-1"
      >
        <span className="border-border flex-1 border-t border-dashed" />
        <Plus className="text-muted-foreground/25 group-hover:text-primary h-3.5 w-3.5 transition-colors" />
        <span className="border-border flex-1 border-t border-dashed" />
      </button>
    );
  }
  return (
    <div className="bg-primary/5 border-primary/25 flex items-center gap-1 rounded-md border border-dashed px-1.5 py-1">
      <span className="text-muted-foreground/60 shrink-0 text-[10px]">插入</span>
      {(Object.keys(ELEMENT_TYPE_META) as CoverElementType[]).map((t) => (
        <button
          key={t}
          type="button"
          onClick={() => onInsert(t)}
          className="border-border text-muted-foreground hover:border-primary/40 hover:text-primary flex items-center gap-0.5 rounded border border-dashed px-1.5 py-0.5 text-[10px] transition-colors"
        >
          <Plus className="h-2.5 w-2.5" /> {ELEMENT_TYPE_META[t].label}
        </button>
      ))}
      <button
        type="button"
        onClick={onToggle}
        aria-label="关闭插入菜单"
        className="text-muted-foreground/50 hover:text-muted-foreground ml-auto rounded p-0.5 transition-colors"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// 主组件：页签 + 元素列表 + 添加页/元素
// ─────────────────────────────────────────────────────────────────────────────

interface CoverElementsEditorProps {
  cover: Cover;
  onChange: (cover: Cover) => void;
}

/** 封面元素编辑器 —— 纯展示 + onChange 回调，父组件负责持有 state 与持久化。 */
export function CoverElementsEditor({
  cover,
  onChange,
}: CoverElementsEditorProps) {
  // 拖拽排序源/悬停目标 + 插入菜单开关（key = `${pageIndex}:${elementIndex}`）
  const [drag, setDrag] = useState<{ from: string; over: string | null } | null>(null);
  const [insertOpen, setInsertOpen] = useState<string | null>(null);
  const keyOf = (pi: number, i: number) => `${pi}:${i}`;

  const updateElement = useCallback(
    (pi: number, id: string, patch: Partial<CoverElement>) => {
      // cover 非空（props 类型保证）→ patchCoverElementsPage 不会返回 null
      onChange(
        patchCoverElementsPage(cover, pi, (els) =>
          els.map((e) => (e.id === id ? { ...e, ...patch } : e)),
        )!,
      );
    },
    [cover, onChange],
  );

  const addElement = useCallback(
    (pi: number, type: CoverElementType) => {
      onChange(
        patchCoverElementsPage(cover, pi, (els) => [
          ...els,
          createElement(type),
        ])!,
      );
    },
    [cover, onChange],
  );

  const removeElement = useCallback(
    (pi: number, id: string) => {
      onChange(
        patchCoverElementsPage(cover, pi, (els) =>
          els.filter((e) => e.id !== id),
        )!,
      );
    },
    [cover, onChange],
  );

  const moveElement = useCallback(
    (pi: number, id: string, dir: -1 | 1) => {
      const page = cover.pages[pi];
      if (!page) return;
      const idx = page.elements.findIndex((e) => e.id === id);
      const j = idx + dir;
      // 越界（首/末元素）或找不到 → 直接跳过 onChange，不产生无意义的新对象
      if (idx < 0 || j < 0 || j >= page.elements.length) return;
      const a = page.elements[idx];
      const b = page.elements[j];
      if (!a || !b) return;
      const next = page.elements.slice();
      next[idx] = b;
      next[j] = a;
      onChange(patchCoverElementsPage(cover, pi, () => next)!);
    },
    [cover, onChange],
  );

  const updateTableCell = useCallback(
    (pi: number, id: string, r: number, c: number, v: string) => {
      onChange(
        patchCoverElementsPage(cover, pi, (els) =>
          els.map((e) => {
            if (e.id !== id || e.type !== "table") return e;
            const rows = e.rows ?? 0;
            const cols = e.cols ?? 0;
            // 重建完整 rows×cols 网格，保证与行/列数始终一致
            const cells = Array.from({ length: rows }, (_, ri) =>
              Array.from({ length: cols }, (_, ci) =>
                ri === r && ci === c ? v : (e.cells?.[ri]?.[ci] ?? ""),
              ),
            );
            return { ...e, cells };
          }),
        )!,
      );
    },
    [cover, onChange],
  );

  const resizeTable = useCallback(
    (pi: number, id: string, dr: number, dc: number) => {
      onChange(
        patchCoverElementsPage(cover, pi, (els) =>
          els.map((e) => {
            if (e.id !== id || e.type !== "table") return e;
            const rows = Math.max(1, (e.rows ?? 0) + dr);
            const cols = Math.max(1, (e.cols ?? 0) + dc);
            // 新增行/列自动补空串，删除行列时末尾单元格被丢弃
            const cells = Array.from({ length: rows }, (_, ri) =>
              Array.from(
                { length: cols },
                (_, ci) => e.cells?.[ri]?.[ci] ?? "",
              ),
            );
            return { ...e, rows, cols, cells };
          }),
        )!,
      );
    },
    [cover, onChange],
  );

  /** 拖拽落点：把元素从 fromIdx 移到 toIdx（splice 两步）。 */
  const moveElementTo = useCallback(
    (pi: number, fromIdx: number, toIdx: number) => {
      const page = cover.pages[pi];
      if (!page) return;
      const els = page.elements.slice();
      if (
        fromIdx < 0 ||
        fromIdx >= els.length ||
        toIdx < 0 ||
        toIdx >= els.length ||
        fromIdx === toIdx
      ) {
        return;
      }
      const [moved] = els.splice(fromIdx, 1);
      if (!moved) return;
      els.splice(toIdx, 0, moved);
      onChange(patchCoverElementsPage(cover, pi, () => els)!);
    },
    [cover, onChange],
  );

  /** 在指定 index 插入新元素（元素间「＋」菜单）。 */
  const insertElement = useCallback(
    (pi: number, index: number, type: CoverElementType) => {
      onChange(
        patchCoverElementsPage(cover, pi, (els) => {
          const next = els.slice();
          next.splice(index, 0, createElement(type));
          return next;
        })!,
      );
      setInsertOpen(null);
    },
    [cover, onChange],
  );

  const addPage = useCallback(() => {
    onChange({ ...cover, pages: [...cover.pages, { elements: [] }] });
  }, [cover, onChange]);

  const removePage = useCallback(
    (pi: number) => {
      if (cover.pages.length <= 1) return;
      onChange({ ...cover, pages: cover.pages.filter((_, i) => i !== pi) });
    },
    [cover, onChange],
  );

  return (
    <div className="space-y-4">
      <p className="text-muted-foreground/70 text-[10px]">
        结构化封面：按页逐元素编辑；绑定下拉的元素在生成时自动填入报告字段值。
      </p>

      {cover.pages.length === 0 ? (
        <div className="border-border bg-muted/20 text-muted-foreground flex flex-col items-center gap-2 rounded-lg border border-dashed py-8 text-xs">
          <p>当前封面没有任何页面</p>
          <button
            type="button"
            onClick={addPage}
            className="bg-primary text-primary-foreground hover:bg-primary/90 flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium shadow-sm transition-all"
          >
            <Plus className="h-3.5 w-3.5" /> 添加第一页
          </button>
        </div>
      ) : (
        cover.pages.map((page, pi) => (
          <div
            key={pi}
            className="border-border bg-card overflow-hidden rounded-xl border"
          >
            {/* 页头 */}
            <div className="border-border bg-muted/30 flex items-center gap-2 border-b px-3 py-2">
              <span className="text-foreground text-xs font-semibold">
                页 {pi + 1}
              </span>
              <span className="text-muted-foreground text-[10px]">
                {page.elements.length} 个元素
              </span>
              <button
                type="button"
                onClick={() => removePage(pi)}
                disabled={cover.pages.length <= 1}
                className="text-muted-foreground hover:text-destructive ml-auto flex items-center gap-1 text-[10px] transition-colors disabled:cursor-not-allowed disabled:opacity-30"
              >
                <Trash2 className="h-3 w-3" /> 删除页
              </button>
            </div>

            {/* 元素列表 */}
            <div className="space-y-2 p-3">
              {page.elements.length === 0 ? (
                <>
                  <InsertZone
                    open={insertOpen === keyOf(pi, 0)}
                    onToggle={() =>
                      setInsertOpen(
                        insertOpen === keyOf(pi, 0) ? null : keyOf(pi, 0),
                      )
                    }
                    onInsert={(t) => insertElement(pi, 0, t)}
                  />
                  <p className="text-muted-foreground/70 rounded-lg border border-dashed py-4 text-center text-[11px]">
                    空页 — 添加元素开始编辑
                  </p>
                </>
              ) : (
                <>
                  <InsertZone
                    open={insertOpen === keyOf(pi, 0)}
                    onToggle={() =>
                      setInsertOpen(
                        insertOpen === keyOf(pi, 0) ? null : keyOf(pi, 0),
                      )
                    }
                    onInsert={(t) => insertElement(pi, 0, t)}
                  />
                  {page.elements.map((el, i) => (
                    <Fragment key={el.id}>
                      <ElementRow
                        el={el}
                        index={i}
                        count={page.elements.length}
                        onPatch={(patch) => updateElement(pi, el.id, patch)}
                        onRemove={() => removeElement(pi, el.id)}
                        onMove={(dir) => moveElement(pi, el.id, dir)}
                        onCell={(r, c, v) =>
                          updateTableCell(pi, el.id, r, c, v)
                        }
                        onResize={(dr, dc) => resizeTable(pi, el.id, dr, dc)}
                        dragging={drag?.from === keyOf(pi, i)}
                        dragOver={drag?.over === keyOf(pi, i)}
                        onDragStart={() =>
                          setDrag({ from: keyOf(pi, i), over: null })
                        }
                        onDragOver={() =>
                          setDrag((d) =>
                            d ? { ...d, over: keyOf(pi, i) } : d,
                          )
                        }
                        onDrop={() => {
                          if (drag && drag.from !== keyOf(pi, i)) {
                            const [fp, fi] = drag.from
                              .split(":")
                              .map(Number);
                            if (fp === pi && fi !== undefined) {
                              moveElementTo(pi, fi, i);
                            }
                          }
                          setDrag(null);
                        }}
                        onDragEnd={() => setDrag(null)}
                      />
                      <InsertZone
                        open={insertOpen === keyOf(pi, i + 1)}
                        onToggle={() =>
                          setInsertOpen(
                            insertOpen === keyOf(pi, i + 1)
                              ? null
                              : keyOf(pi, i + 1),
                          )
                        }
                        onInsert={(t) => insertElement(pi, i + 1, t)}
                      />
                    </Fragment>
                  ))}
                </>
              )}

              {/* 添加元素按钮组 */}
              <div className="flex flex-wrap items-center gap-1.5 pt-1">
                <span className="text-muted-foreground text-[10px]">
                  添加：
                </span>
                {(Object.keys(ELEMENT_TYPE_META) as CoverElementType[]).map(
                  (t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => addElement(pi, t)}
                      className="border-border text-muted-foreground hover:border-primary/40 hover:text-primary flex items-center gap-1 rounded-md border border-dashed px-2 py-1 text-[11px] transition-colors"
                    >
                      <Plus className="h-3 w-3" /> {ELEMENT_TYPE_META[t].label}
                    </button>
                  ),
                )}
              </div>
            </div>
          </div>
        ))
      )}

      <button
        type="button"
        onClick={addPage}
        className="border-border text-primary hover:bg-primary/5 flex w-full items-center justify-center gap-1.5 rounded-lg border border-dashed py-2 text-sm transition-colors"
      >
        <Plus className="h-4 w-4" /> 添加页面
      </button>
    </div>
  );
}
