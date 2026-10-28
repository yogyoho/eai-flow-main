"use client";

import {
  CircleDot,
  CirclePlay,
  Diamond,
  GitBranch,
  Rows3,
  Split,
  SquareStack,
} from "lucide-react";
import type { NodeTypeName } from "@/lib/types";
import { NODE_TYPE_META } from "./nodeRegistry";
import { cn } from "@/lib/utils";

const PALETTE: {
  type: NodeTypeName;
  icon: React.ComponentType<{ className?: string; style?: React.CSSProperties }>;
}[] = [
  { type: "start", icon: CirclePlay },
  { type: "between", icon: SquareStack },
  { type: "end", icon: CircleDot },
  { type: "serial", icon: Split },
  { type: "parallel", icon: GitBranch },
  { type: "inclusive", icon: Diamond },
];

export function DesignerSidebar({
  onAdd,
}: {
  onAdd: (type: NodeTypeName) => void;
}) {
  return (
    <aside className="hidden w-[236px] shrink-0 flex-col border-r border-border bg-card/70 xl:flex">
      <div className="border-b border-border px-4 py-3.5">
        <p className="text-[12px] font-semibold">节点面板</p>
        <p className="mt-0.5 text-[11px] text-muted-foreground">
          拖拽节点到画布，或点击添加
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-3">
        <div className="grid grid-cols-2 gap-2">
          {PALETTE.map(({ type, icon: Icon }) => {
            const meta = NODE_TYPE_META[type];
            return (
              <button
                key={type}
                type="button"
                draggable
                onDragStart={(event) => {
                  event.dataTransfer.setData("application/x-flow-node", type);
                  event.dataTransfer.effectAllowed = "move";
                }}
                onClick={() => onAdd(type)}
                className="group flex cursor-grab flex-col items-center gap-2 rounded-xl border border-border bg-card px-2 py-3 transition hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-[0_8px_18px_-12px_rgba(16,24,40,0.35)] active:cursor-grabbing"
              >
                <span
                  className="flex h-8 w-8 items-center justify-center rounded-lg"
                  style={{ backgroundColor: `rgba(${meta.rgb}, 0.10)`, color: meta.color }}
                >
                  <Icon className="h-4 w-4" style={{ color: meta.color }} />
                </span>
                <span className="text-[11.5px] font-medium">{meta.short}</span>
              </button>
            );
          })}
        </div>

        <div className="mt-5 rounded-xl border border-border bg-muted/30 p-3">
          <p className="text-[11px] font-semibold text-foreground">画布提示</p>
          <ul className="mt-2 space-y-1.5 text-[10.5px] leading-relaxed text-muted-foreground">
            <li>· 拖动节点边缘锚点连接跳转</li>
            <li>· 选中节点或连线后可在右侧编辑</li>
            <li>· Delete 删除，Ctrl/⌘ + S 保存</li>
            <li>· 退回分支请把跳转类型设为「退回」</li>
          </ul>
        </div>

        <div className="mt-4 space-y-2">
          {(["start", "between", "end", "serial", "parallel", "inclusive"] as NodeTypeName[]).map(
            (type) => (
              <div key={type} className="flex items-center gap-2 text-[10.5px] text-muted-foreground">
                <span
                  className={cn("h-1.5 w-1.5 rounded-full")}
                  style={{ backgroundColor: NODE_TYPE_META[type].color }}
                />
                {NODE_TYPE_META[type].label}
              </div>
            ),
          )}
        </div>
      </div>

      <div className="border-t border-border px-4 py-3">
        <div className="flex items-center gap-2 text-[10.5px] text-muted-foreground">
          <Rows3 className="h-3.5 w-3.5" />
          数据契约：warm-flow DefJson
        </div>
      </div>
    </aside>
  );
}
