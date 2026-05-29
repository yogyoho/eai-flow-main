"use client";

import { useCallback, useState } from "react";
import { Background, Controls, MiniMap, ReactFlow, type NodeTypes } from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { AIGenerateNode } from "./nodes/AIGenerateNode";
import { ConditionNode } from "./nodes/ConditionNode";
import { MergeNode } from "./nodes/MergeNode";
import { PhaseNode } from "./nodes/PhaseNode";
import { ReviewNode } from "./nodes/ReviewNode";
import { NodePalette } from "./panels/NodePalette";
import { useValidation } from "./hooks/useValidation";
import { useWorkflowDAG } from "./hooks/useWorkflowDAG";
import { workflowApi } from "./api";

const nodeTypes: NodeTypes = {
  phase: PhaseNode,
  review: ReviewNode,
  condition: ConditionNode,
  ai_generate: AIGenerateNode,
  merge: MergeNode,
};

interface WorkflowEditorProps {
  projectId: string;
}

export function WorkflowEditor({ projectId }: WorkflowEditorProps) {
  const { nodes, edges, onNodesChange, onEdgesChange, onConnect, toGraphJson } = useWorkflowDAG();
  const { result: validationResult, isValidating, validate } = useValidation();
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState("新工作流");

  const handleValidate = useCallback(async () => {
    await validate(toGraphJson());
  }, [validate, toGraphJson]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      await workflowApi.create({ name, graphJson: toGraphJson() });
    } finally {
      setSaving(false);
    }
  }, [name, toGraphJson]);

  return (
    <div className="relative flex h-full border rounded-lg overflow-hidden">
      {/* Left: Node Palette */}
      <div className="w-48 shrink-0 border-r bg-muted/30 p-3">
        <div className="text-sm font-semibold mb-3">节点面板</div>
        <NodePalette />
      </div>

      {/* Center: React Flow Canvas */}
      <div className="flex-1">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          nodeTypes={nodeTypes}
          fitView
        >
          <Background />
          <Controls />
          <MiniMap />
        </ReactFlow>
      </div>

      {/* Top toolbar */}
      <div className="absolute top-2 right-2 z-10 flex gap-2">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="px-2 py-1 text-sm border rounded bg-white"
          placeholder="工作流名称"
        />
        <button
          onClick={handleValidate}
          disabled={isValidating}
          className="px-3 py-1 text-sm bg-secondary rounded hover:bg-secondary/80"
        >
          {isValidating ? "校验中..." : "校验"}
        </button>
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-3 py-1 text-sm bg-primary text-primary-foreground rounded hover:bg-primary/90"
        >
          {saving ? "保存中..." : "保存"}
        </button>
      </div>

      {/* Validation result overlay */}
      {validationResult && (
        <div
          className={`absolute bottom-2 right-2 z-10 p-3 rounded-lg border text-sm max-w-xs ${
            validationResult.valid ? "bg-green-50 border-green-200" : "bg-red-50 border-red-200"
          }`}
        >
          <div className="font-semibold">
            {validationResult.valid ? "校验通过" : "校验失败"}
          </div>
          {validationResult.errors.map((e, i) => (
            <div key={i} className="text-red-600">
              {e}
            </div>
          ))}
          {validationResult.warnings.map((w, i) => (
            <div key={i} className="text-amber-600">
              {w}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
