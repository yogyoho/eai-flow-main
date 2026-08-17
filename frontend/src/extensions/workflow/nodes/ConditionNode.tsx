"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";

import type { DAGNodeData } from "../types";

export function ConditionNode({
  data,
  selected,
}: NodeProps & { data: DAGNodeData }) {
  return (
    <div className="relative h-20 w-20">
      <Handle
        type="target"
        position={Position.Top}
        className="!h-2 !w-2 !bg-amber-400"
      />
      <div
        className={`absolute inset-2 flex items-center justify-center border-2 ${
          selected ? "border-amber-500 shadow-lg" : "border-amber-300"
        } bg-amber-50`}
        style={{ transform: "rotate(45deg)", borderRadius: 4 }}
      >
        <span
          className="text-center text-[10px] leading-tight font-medium text-amber-800"
          style={{ transform: "rotate(-45deg)" }}
        >
          {/* EAI-CUSTOM: `||` is deliberate — new condition nodes are created with expression: ""
              (NodePalette / useWorkflowDAG) and the config panel allows clearing it, so the falsy-string
              fallback to label/`条件` is required behavior. `??` would render a blank diamond. */}
          {/* eslint-disable-next-line @typescript-eslint/prefer-nullish-coalescing -- `??` changes behavior when expression is "" */}
          {data.expression || data.label || "条件"}
        </span>
      </div>
      <Handle
        type="source"
        position={Position.Bottom}
        className="!h-2 !w-2 !bg-amber-400"
      />
    </div>
  );
}
