"use client";

import { useReactFlow } from "@xyflow/react";

import type { DAGNodeData, DAGNodeType } from "../types";

const NODE_TYPES: { type: DAGNodeType; label: string; color: string; icon: string }[] = [
  { type: "phase", label: "阶段", color: "purple", icon: "⬡" },
  { type: "review", label: "审核", color: "red", icon: "✓" },
  { type: "condition", label: "条件", color: "amber", icon: "◇" },
  { type: "ai_generate", label: "AI生成", color: "blue", icon: "✦" },
  { type: "merge", label: "汇聚", color: "green", icon: "⊕" },
  { type: "sub_workflow", label: "子流程", color: "indigo", icon: "⊞" },
];

const COLOR_CLASSES: Record<string, { bg: string; border: string; text: string; hover: string; iconBg: string }> = {
  purple: { bg: "bg-purple-50", border: "border-purple-200", text: "text-purple-700", hover: "hover:bg-purple-100 hover:border-purple-300 hover:shadow-sm", iconBg: "bg-purple-100" },
  red: { bg: "bg-red-50", border: "border-red-200", text: "text-red-700", hover: "hover:bg-red-100 hover:border-red-300 hover:shadow-sm", iconBg: "bg-red-100" },
  amber: { bg: "bg-amber-50", border: "border-amber-200", text: "text-amber-700", hover: "hover:bg-amber-100 hover:border-amber-300 hover:shadow-sm", iconBg: "bg-amber-100" },
  blue: { bg: "bg-blue-50", border: "border-blue-200", text: "text-blue-700", hover: "hover:bg-blue-100 hover:border-blue-300 hover:shadow-sm", iconBg: "bg-blue-100" },
  green: { bg: "bg-green-50", border: "border-green-200", text: "text-green-700", hover: "hover:bg-green-100 hover:border-green-300 hover:shadow-sm", iconBg: "bg-green-100" },
  indigo: { bg: "bg-indigo-50", border: "border-indigo-200", text: "text-indigo-700", hover: "hover:bg-indigo-100 hover:border-indigo-300 hover:shadow-sm", iconBg: "bg-indigo-100" },
};

export function NodePalette() {
  const { addNodes, screenToFlowPosition } = useReactFlow();

  const handleAddNode = (type: DAGNodeType) => {
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
      sub_workflow: { label: "新子流程" },
    };

    addNodes({
      id,
      type,
      position,
      data: defaultData[type],
    });
  };

  return (
    <div className="flex flex-col gap-1.5">
      {NODE_TYPES.map(({ type, label, color, icon }) => {
        const colors = COLOR_CLASSES[color]!;
        return (
          <button
            key={type}
            onClick={() => handleAddNode(type)}
            className={`flex items-center gap-2 px-2.5 py-2 rounded-lg border text-xs font-medium transition-all cursor-pointer ${colors.bg} ${colors.border} ${colors.text} ${colors.hover}`}
          >
            <span className={`w-5 h-5 rounded flex items-center justify-center text-[10px] ${colors.iconBg} font-bold`}>
              {icon}
            </span>
            {label}
          </button>
        );
      })}
    </div>
  );
}
