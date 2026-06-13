"use client";

import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useState } from "react";
import { Background, Controls, MiniMap, ReactFlow, ReactFlowProvider, type NodeTypes, type EdgeTypes } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { ChevronRight, Layers, Trash2 } from "lucide-react";

import { AIGenerateNode } from "./nodes/AIGenerateNode";
import { ConditionNode } from "./nodes/ConditionNode";
import { MergeNode } from "./nodes/MergeNode";
import { ReviewNode } from "./nodes/ReviewNode";
import { SubflowNode } from "./nodes/SubflowNode";
import { TaskNode } from "./nodes/TaskNode";
import { AnimatedFlowEdge } from "./edges/AnimatedFlowEdge";
import { ConditionEdge } from "./edges/ConditionEdge";
import { NodePalette } from "./panels/NodePalette";
import { AIGenerateConfigPanel } from "./panels/AIGenerateConfigPanel";
import { ConditionConfigPanel } from "./panels/ConditionConfigPanel";
import { MergeConfigPanel } from "./panels/MergeConfigPanel";
import { ReviewConfigPanel } from "./panels/ReviewConfigPanel";
import { SubflowConfigPanel } from "./panels/SubflowConfigPanel";
import { TaskConfigPanel } from "./panels/TaskConfigPanel";
import { useValidation } from "./hooks/useValidation";
import { useWorkflowDAG } from "./hooks/useWorkflowDAG";
import { workflowApi } from "./api";
import type { DAGNode, DAGNodeData, WorkflowGraph } from "./types";

const nodeTypes: NodeTypes = {
  review: ReviewNode,
  condition: ConditionNode,
  ai_generate: AIGenerateNode,
  merge: MergeNode,
  task: TaskNode,
  subflow: SubflowNode,
};

const edgeTypes: EdgeTypes = {
  condition: ConditionEdge,
  animated: AnimatedFlowEdge,
};

/** Imperative handle exposed via ref when hideToolbar is true. */
export interface WorkflowEditorHandle {
  validate: () => Promise<void>;
  save: () => Promise<void>;
}

export interface WorkflowEditorProps {
  projectId?: string;
  initialGraphJson?: WorkflowGraph;
  initialName?: string;
  onSave?: (name: string, graphJson: WorkflowGraph) => Promise<void>;
  onSaveTemplate?: (name: string, graphJson: WorkflowGraph) => Promise<void>;
  onOrgBindingChange?: (nodeId: string, deptCode: string | null) => void;
  orgBindings?: Record<string, { deptCode?: string }>;
  /** Hide the built-in toolbar. Parent provides its own buttons via ref. */
  hideToolbar?: boolean;
  /** When true, the workflow canvas is view-only — no editing, no drag, no save. */
  readOnly?: boolean;
}

const NODE_TYPE_LABELS: Record<string, string> = {
  review: "审核节点",
  condition: "条件节点",
  ai_generate: "AI 生成节点",
  merge: "汇聚节点",
  task: "任务节点",
  subflow: "子流程",
};

export const WorkflowEditor = forwardRef<WorkflowEditorHandle, WorkflowEditorProps>(function WorkflowEditor(
  {
    projectId,
    initialGraphJson,
    initialName,
    onSave: onSaveProp,
    onSaveTemplate: onSaveTemplateProp,
    onOrgBindingChange,
    orgBindings,
    hideToolbar,
    readOnly = false,
  },
  ref,
) {
  const { nodes, edges, onNodesChange, onEdgesChange, onConnect, updateNodeData, removeNode, toGraphJson, fromGraphJson, enterSubflow, exitSubflow } = useWorkflowDAG();
  const { result: validationResult, isValidating, validate } = useValidation();
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState(initialName || "新工作流");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  /** ID of the subflow node we are currently inside, or null when on main graph. */
  const [activeSubflowId, setActiveSubflowId] = useState<string | null>(null);
  /** Label of the active subflow for the breadcrumb. */
  const activeSubflowLabel = useMemo(() => {
    if (!activeSubflowId) return null;
    // Find the label from the main graph's node data
    const graphJson = toGraphJson();
    const mainNode = graphJson.mainGraph?.nodes?.find((n) => n.id === activeSubflowId);
    return mainNode?.data?.label ?? activeSubflowId;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSubflowId]);

  // Derive selected node from the latest nodes array so the property panel
  // always reflects the current data (including edits made via updateNodeData).
  const selectedNode = useMemo<DAGNode | null>(
    () => {
      if (!selectedNodeId) return null;
      const n = nodes.find((n) => n.id === selectedNodeId);
      return n ?? null;
    },
    [selectedNodeId, nodes],
  );

  useEffect(() => {
    if (initialGraphJson) {
      fromGraphJson(initialGraphJson);
    }
  }, [initialGraphJson, fromGraphJson]);

  const handleValidate = useCallback(async () => {
    await validate(toGraphJson());
  }, [validate, toGraphJson]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      const json = toGraphJson();
      if (onSaveProp) {
        await onSaveProp(name, json);
      } else {
        await workflowApi.create({ name, graphJson: json });
      }
    } finally {
      setSaving(false);
    }
  }, [name, toGraphJson, onSaveProp]);

  const handleSaveTemplate = useCallback(async () => {
    setSaving(true);
    try {
      const json = toGraphJson();
      if (onSaveTemplateProp) {
        await onSaveTemplateProp(name, json);
      } else {
        await workflowApi.create({ name: name + " (模板)", graphJson: json, isTemplate: true });
      }
    } finally {
      setSaving(false);
    }
  }, [name, toGraphJson, onSaveTemplateProp]);

  // Expose imperative methods to parent
  useImperativeHandle(ref, () => ({
    validate: handleValidate,
    save: handleSave,
  }), [handleValidate, handleSave]);

  const getOrgDeptCode = useCallback(
    (nodeId: string): string | undefined => {
      if (!orgBindings || !orgBindings[nodeId]) return undefined;
      return orgBindings[nodeId].deptCode;
    },
    [orgBindings],
  );

  const handleDeleteSelected = useCallback(() => {
    if (selectedNodeId) {
      removeNode(selectedNodeId);
      setSelectedNodeId(null);
    }
  }, [selectedNodeId, removeNode]);

  /** Double-click a subflow node → enter its inner graph. */
  const handleNodeDoubleClick = useCallback((_event: React.MouseEvent, node: DAGNode) => {
    if (node.type !== "subflow" || readOnly) return;
    enterSubflow(node.id);
    setActiveSubflowId(node.id);
    setSelectedNodeId(null);
  }, [enterSubflow, readOnly]);

  /** Exit subflow → return to main graph. */
  const handleExitSubflow = useCallback(() => {
    if (!activeSubflowId) return;
    exitSubflow(activeSubflowId);
    setActiveSubflowId(null);
    setSelectedNodeId(null);
  }, [activeSubflowId, exitSubflow]);

  /** Render the appropriate config panel for the selected node type. */
  const renderConfigPanel = (node: DAGNode) => {
    switch (node.type) {
      case "review":
        return <ReviewConfigPanel data={node.data} onUpdate={(partial) => updateNodeData(node.id, partial)} />;
      case "condition":
        return <ConditionConfigPanel data={node.data} onUpdate={(partial) => updateNodeData(node.id, partial)} />;
      case "ai_generate":
        return <AIGenerateConfigPanel data={node.data} onUpdate={(partial) => updateNodeData(node.id, partial)} />;
      case "merge":
        return <MergeConfigPanel data={node.data} onUpdate={(partial) => updateNodeData(node.id, partial)} />;
      case "task":
        return (
          <TaskConfigPanel
            data={node.data}
            nodeId={node.id}
            onUpdate={(partial) => updateNodeData(node.id, partial)}
            orgDeptCode={getOrgDeptCode(node.id)}
            onOrgBindingChange={onOrgBindingChange}
          />
        );
      case "subflow":
        return (
          <SubflowConfigPanel
            data={node.data}
            nodeId={node.id}
            onUpdate={(partial) => updateNodeData(node.id, partial)}
            orgDeptCode={getOrgDeptCode(node.id)}
            onOrgBindingChange={onOrgBindingChange}
          />
        );
      default:
        return (
          <div className="p-4 text-xs text-muted-foreground">
            {node.type} 节点暂无可配置属性
          </div>
        );
    }
  };

  return (
    <ReactFlowProvider>
    <div className="relative flex h-full overflow-hidden">
      {/* Left: Node Palette — hidden in readOnly mode */}
      {!readOnly && (
      <div className="w-52 shrink-0 border-r border-border bg-muted/30 flex flex-col">
        <div className="px-3 pt-3 pb-2">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">节点面板</div>
        </div>
        <div className="px-3 pb-3 flex-1 overflow-y-auto">
          <NodePalette />
        </div>
      </div>
      )}

      {/* Center: Canvas */}
      <div className="flex-1">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={readOnly ? undefined : onNodesChange}
          onEdgesChange={readOnly ? undefined : onEdgesChange}
          onConnect={readOnly ? undefined : onConnect}
          onNodeClick={(_event, node) => {
            setSelectedNodeId(node.id);
          }}
          onNodeDoubleClick={handleNodeDoubleClick}
          onPaneClick={() => {
            setSelectedNodeId(null);
          }}
          deleteKeyCode={readOnly ? null : ["Backspace", "Delete"]}
          nodesDraggable={!readOnly}
          nodesConnectable={!readOnly}
          elementsSelectable={!readOnly}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          fitView
          proOptions={{ hideAttribution: true }}
        >
          <Background />
          <Controls showInteractive={false} />
          <MiniMap />
        </ReactFlow>

        {/* Subflow breadcrumb navigation */}
        {activeSubflowId && (
          <div className="absolute left-4 top-4 z-10 flex items-center gap-1 rounded-lg bg-background/90 backdrop-blur-sm border border-violet-200 px-3 py-1.5 shadow-sm">
            <button
              type="button"
              onClick={handleExitSubflow}
              className="text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
            >
              主流程
            </button>
            <ChevronRight className="w-3 h-3 text-muted-foreground/50" />
            <div className="flex items-center gap-1.5 text-xs font-semibold text-violet-700">
              <Layers className="w-3 h-3" />
              {activeSubflowLabel}
            </div>
            <button
              type="button"
              onClick={handleExitSubflow}
              className="ml-2 px-2 py-0.5 text-[10px] font-medium text-violet-600 bg-violet-50 border border-violet-200 rounded-md hover:bg-violet-100 transition-colors"
            >
              ← 返回主流程
            </button>
          </div>
        )}

        {readOnly && !activeSubflowId && (
          <div className="pointer-events-none absolute left-4 top-4 rounded-md bg-background/80 px-3 py-1.5 text-xs font-medium text-muted-foreground backdrop-blur-sm border border-border">
            只读模式 — 工作流已锁定
          </div>
        )}
      </div>

      {/* Right: Property panel */}
      <div className="w-72 shrink-0 border-l border-border bg-card overflow-y-auto">
        {selectedNode ? (
          <div className="divide-y divide-border">
            <div className="px-4 py-3 bg-muted/30 flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="text-sm font-semibold text-foreground truncate">
                  {selectedNode.data.label || selectedNode.id}
                </div>
                <div className="text-[10px] text-muted-foreground mt-0.5">
                  {NODE_TYPE_LABELS[selectedNode.type] ?? selectedNode.type}
                </div>
              </div>
              <button
                onClick={handleDeleteSelected}
                className="shrink-0 p-1.5 text-muted-foreground/60 hover:text-red-500 hover:bg-red-50 rounded-md transition-colors"
                title="删除节点 (Delete)"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
            <div>
              {renderConfigPanel(selectedNode)}
            </div>
          </div>
        ) : (
          <div className="p-6 flex flex-col items-center justify-center text-center gap-2 min-h-[200px]">
            <div className="w-10 h-10 rounded-full bg-muted/50 flex items-center justify-center">
              <svg className="w-5 h-5 text-muted-foreground/50" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122" /></svg>
            </div>
            <div className="text-xs text-muted-foreground">点击画布中的节点<br/>查看和编辑属性</div>
            <div className="text-[10px] text-muted-foreground/60 mt-1">按 Delete 键可删除选中节点</div>
          </div>
        )}
      </div>

      {/* Built-in toolbar — only shown when NOT using external toolbar AND NOT readOnly */}
      {!hideToolbar && !readOnly && (
        <div className="absolute top-2 right-2 z-10 flex gap-1.5 bg-background/90 backdrop-blur-sm rounded-lg border border-border p-1.5 shadow-sm">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="px-2.5 py-1 text-sm border border-border rounded-md bg-background focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/40"
            placeholder="工作流名称"
          />
          <button
            onClick={handleValidate}
            disabled={isValidating}
            className="px-2.5 py-1 text-xs font-medium bg-secondary text-secondary-foreground rounded-md hover:bg-secondary/80 transition-colors"
          >
            {isValidating ? "校验中..." : "校验"}
          </button>
          {!onSaveTemplateProp && (
            <button
              onClick={handleSaveTemplate}
              disabled={saving}
              className="px-2.5 py-1 text-xs font-medium bg-muted text-muted-foreground rounded-md hover:bg-muted/80 transition-colors"
            >
              存为模板
            </button>
          )}
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-2.5 py-1 text-xs font-medium bg-primary text-primary-foreground rounded-md hover:bg-primary/90 transition-colors"
          >
            {saving ? "保存中..." : "保存"}
          </button>
        </div>
      )}

      {/* Validation result overlay */}
      {validationResult && (
        <div
          className={`absolute bottom-3 left-52 right-72 z-10 mx-4 p-3 rounded-lg border text-sm max-w-sm shadow-lg ${
            validationResult.valid ? "bg-green-50 border-green-200" : "bg-red-50 border-red-200"
          }`}
        >
          <div className="font-semibold flex items-center gap-1.5">
            <span>{validationResult.valid ? "✓" : "✗"}</span>
            {validationResult.valid ? "校验通过" : "校验失败"}
          </div>
          {validationResult.errors.map((e, i) => (
            <div key={i} className="text-red-600 text-xs mt-1">{e}</div>
          ))}
          {validationResult.warnings.map((w, i) => (
            <div key={i} className="text-amber-600 text-xs mt-1">{w}</div>
          ))}
        </div>
      )}
    </div>
    </ReactFlowProvider>
  );
});
