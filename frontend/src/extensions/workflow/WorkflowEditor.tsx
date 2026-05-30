"use client";

import { useCallback, useState } from "react";
import { Background, Controls, MiniMap, ReactFlow, type NodeTypes, type EdgeTypes } from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { AIGenerateNode } from "./nodes/AIGenerateNode";
import { ConditionNode } from "./nodes/ConditionNode";
import { MergeNode } from "./nodes/MergeNode";
import { PhaseNode } from "./nodes/PhaseNode";
import { ReviewNode } from "./nodes/ReviewNode";
import { ConditionEdge } from "./edges/ConditionEdge";
import { NodePalette } from "./panels/NodePalette";
import { PhaseConfigPanel } from "./panels/PhaseConfigPanel";
import { ReviewConfigPanel } from "./panels/ReviewConfigPanel";
import { useValidation } from "./hooks/useValidation";
import { useWorkflowDAG } from "./hooks/useWorkflowDAG";
import { workflowApi } from "./api";
import type { DAGNode, DAGNodeData } from "./types";

const nodeTypes: NodeTypes = {
  phase: PhaseNode,
  review: ReviewNode,
  condition: ConditionNode,
  ai_generate: AIGenerateNode,
  merge: MergeNode,
};

const edgeTypes: EdgeTypes = {
  condition: ConditionEdge,
};

interface WorkflowEditorProps {
  projectId: string;
}

export function WorkflowEditor({ projectId }: WorkflowEditorProps) {
  const { nodes, edges, onNodesChange, onEdgesChange, onConnect, updateNodeData, toGraphJson } = useWorkflowDAG();
  const { result: validationResult, isValidating, validate } = useValidation();
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState("新工作流");
  const [selectedNode, setSelectedNode] = useState<DAGNode | null>(null);

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

  const handleSaveTemplate = useCallback(async () => {
    setSaving(true);
    try {
      await workflowApi.create({ name: name + " (模板)", graphJson: toGraphJson(), isTemplate: true });
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
          onNodeClick={(_event, node) => {
            const dagNode: DAGNode = {
              id: node.id,
              type: node.type as DAGNode["type"],
              position: node.position,
              data: node.data as DAGNodeData,
            };
            setSelectedNode(dagNode);
          }}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          fitView
        >
          <Background />
          <Controls />
          <MiniMap />
        </ReactFlow>
      </div>

      {/* Right: Config Panel */}
      <div className="w-72 shrink-0 border-l bg-card overflow-y-auto">
        {selectedNode ? (
          <div className="p-4 space-y-3">
            <div className="text-sm font-semibold">
              {selectedNode.data.label || selectedNode.id} 属性
            </div>
            {selectedNode.type === "phase" && (
              <PhaseConfigPanel
                data={selectedNode.data}
                onUpdate={(partial) => updateNodeData(selectedNode.id, partial)}
              />
            )}
            {selectedNode.type === "review" && (
              <ReviewConfigPanel
                data={selectedNode.data}
                onUpdate={(partial) => updateNodeData(selectedNode.id, partial)}
              />
            )}
            {selectedNode.type !== "phase" && selectedNode.type !== "review" && (
              <div className="text-xs text-muted-foreground">
                {selectedNode.type} 节点暂无可配置属性
              </div>
            )}
          </div>
        ) : (
          <div className="p-4 text-sm text-muted-foreground">
            选择节点查看属性
          </div>
        )}
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
          onClick={handleSaveTemplate}
          disabled={saving}
          className="px-3 py-1 text-sm bg-muted rounded hover:bg-muted/80"
        >
          存为模板
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
