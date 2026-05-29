"use client";

import { useReactFlow } from "@xyflow/react";

import type { DAGNodeData, DAGNodeType } from "../types";

const NODE_TYPES: { type: DAGNodeType; label: string; color: string }[] = [
  { type: "phase", label: "阶段", color: "purple" },
  { type: "review", label: "审核", color: "red" },
  { type: "condition", label: "条件", color: "amber" },
  { type: "ai_generate", label: "AI生成", color: "blue" },
  { type: "merge", label: "汇聚", color: "green" },
];

const COLOR_CLASSES: Record<string, { bg: string; border: string; text: string }> = {
  purple: { bg: "bg-purple-50", border: "border-purple-200", text: "text-purple-700" },
  red: { bg: "bg-red-50", border: "border-red-200", text: "text-red-700" },
  amber: { bg: "bg-amber-50", border: "border-amber-200", text: "text-amber-700" },
  blue: { bg: "bg-blue-50", border: "border-blue-200", text: "text-blue-700" },
  green: { bg: "bg-green-50", border: "border-green-200", text: "text-green-700" },
};

export function NodePalette() {
  const { addNodes, screenToFlowPosition } = useReactFlow();

  const handleAddNode = (type: DAGNodeType) => {
    // Place new node near center of viewport with slight random offset
    const centerX = window.innerWidth / 2 - 100;
    const centerY = window.innerHeight / 2 - 100;
    const offsetX = Math.random() * 80 - 40;
    const offsetY = Math.random() * 80 - 40;
    const position = screenToFlowPosition({
      x: centerX + offsetX,
      y: centerY + offsetY,
    });

    const id = `${type}-${Date.now()}`;
    const defaultData: Record<DAGNodeType, DAGNodeData> = {
      phase: { label: "新阶段" },
      review: { label: "新审核", mode: "chapter" },
      condition: { label: "新条件", expression: "" },
      ai_generate: { label: "AI 生成", aiAssist: true },
      merge: { label: "汇聚" },
    };

    addNodes({
      id,
      type,
      position,
      data: defaultData[type],
    });
  };

  return (
    <div className="flex flex-col gap-2">
      {NODE_TYPES.map(({ type, label, color }) => {
        const colors = COLOR_CLASSES[color]!;
        return (
          <button
            key={type}
            onClick={() => handleAddNode(type)}
            className={`flex items-center gap-2 px-2 py-1.5 rounded-md border text-xs font-medium transition-colors hover:shadow-sm cursor-pointer ${colors.bg} ${colors.border} ${colors.text}`}
          >
            <span className="w-2.5 h-2.5 rounded-sm border" />
            {label}
          </button>
        );
      })}
    </div>
  );
}
