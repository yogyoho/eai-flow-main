"use client";

import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  type NodeTypes,
  type EdgeTypes,
} from "@xyflow/react";
import { ChevronRight, Layers, Trash2 } from "lucide-react";
import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useState,
} from "react";
import "@xyflow/react/dist/style.css";

import { workflowApi } from "./api";
import { AnimatedFlowEdge } from "./edges/AnimatedFlowEdge";
import { ConditionEdge } from "./edges/ConditionEdge";
import { useValidation } from "./hooks/useValidation";
import { useWorkflowDAG } from "./hooks/useWorkflowDAG";
import { AIGenerateNode } from "./nodes/AIGenerateNode";
import { ConditionNode } from "./nodes/ConditionNode";
import { MergeNode } from "./nodes/MergeNode";
import { ReviewNode } from "./nodes/ReviewNode";
import { SubflowNode } from "./nodes/SubflowNode";
import { TaskNode } from "./nodes/TaskNode";
import { AIGenerateConfigPanel } from "./panels/AIGenerateConfigPanel";
import { ConditionConfigPanel } from "./panels/ConditionConfigPanel";
import { MergeConfigPanel } from "./panels/MergeConfigPanel";
import { NodePalette } from "./panels/NodePalette";
import { ReviewConfigPanel } from "./panels/ReviewConfigPanel";
import { SubflowConfigPanel } from "./panels/SubflowConfigPanel";
import { TaskConfigPanel } from "./panels/TaskConfigPanel";
import type { DAGNode, WorkflowGraph } from "./types";

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

export const WorkflowEditor = forwardRef<
  WorkflowEditorHandle,
  WorkflowEditorProps
>(function WorkflowEditor(
  {
    projectId: _projectId,
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
  const {
    nodes,
    edges,
    onNodesChange,
    onEdgesChange,
    onConnect,
    updateNodeData,
    removeNode,
    toGraphJson,
    fromGraphJson,
    enterSubflow,
    exitSubflow,
  } = useWorkflowDAG();
  const { result: validationResult, isValidating, validate } = useValidation();
  const [saving, setSaving] = useState(false);
  // truthiness fallback preserved: empty-string initialName still defaults to "新工作流"
  const [name, setName] = useState(
    initialName != null && initialName !== "" ? initialName : "新工作流",
  );
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  /** ID of the subflow node we are currently inside, or null when on main graph. */
  const [activeSubflowId, setActiveSubflowId] = useState<string | null>(null);
  /** Label of the active subflow for the breadcrumb. */
  const activeSubflowLabel = useMemo(() => {
    if (!activeSubflowId) return null;
    // Find the label from the main graph's node data
    const graphJson = toGraphJson();
    const mainNode = graphJson.mainGraph?.nodes?.find(
      (n) => n.id === activeSubflowId,
    );
    return mainNode?.data?.label ?? activeSubflowId;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSubflowId]);

  // Derive selected node from the latest nodes array so the property panel
  // always reflects the current data (including edits made via updateNodeData).
  const selectedNode = useMemo<DAGNode | null>(() => {
    if (!selectedNodeId) return null;
    const n = nodes.find((n) => n.id === selectedNodeId);
    return n ?? null;
  }, [selectedNodeId, nodes]);

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
        await workflowApi.create({
          name: name + " (模板)",
          graphJson: json,
          isTemplate: true,
        });
      }
    } finally {
      setSaving(false);
    }
  }, [name, toGraphJson, onSaveTemplateProp]);

  // Expose imperative methods to parent
  useImperativeHandle(
    ref,
    () => ({
      validate: handleValidate,
      save: handleSave,
    }),
    [handleValidate, handleSave],
  );

  const getOrgDeptCode = useCallback(
    (nodeId: string): string | undefined => {
      if (!orgBindings?.[nodeId]) return undefined;
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
  const handleNodeDoubleClick = useCallback(
    (_event: React.MouseEvent, node: DAGNode) => {
      if (node.type !== "subflow" || readOnly) return;
      enterSubflow(node.id);
      setActiveSubflowId(node.id);
      setSelectedNodeId(null);
    },
    [enterSubflow, readOnly],
  );

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
        return (
          <ReviewConfigPanel
            data={node.data}
            onUpdate={(partial) => updateNodeData(node.id, partial)}
          />
        );
      case "condition":
        return (
          <ConditionConfigPanel
            data={node.data}
            onUpdate={(partial) => updateNodeData(node.id, partial)}
          />
        );
      case "ai_generate":
        return (
          <AIGenerateConfigPanel
            data={node.data}
            onUpdate={(partial) => updateNodeData(node.id, partial)}
          />
        );
      case "merge":
        return (
          <MergeConfigPanel
            data={node.data}
            onUpdate={(partial) => updateNodeData(node.id, partial)}
          />
        );
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
          <div className="text-muted-foreground p-4 text-xs">
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
          <div className="border-border bg-muted/30 flex w-52 shrink-0 flex-col border-r">
            <div className="px-3 pt-3 pb-2">
              <div className="text-muted-foreground text-[11px] font-semibold tracking-wider uppercase">
                节点面板
              </div>
            </div>
            <div className="flex-1 overflow-y-auto px-3 pb-3">
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
            <div className="bg-background/90 absolute top-4 left-4 z-10 flex items-center gap-1 rounded-lg border border-violet-200 px-3 py-1.5 shadow-sm backdrop-blur-sm">
              <button
                type="button"
                onClick={handleExitSubflow}
                className="text-muted-foreground hover:text-foreground text-xs font-medium transition-colors"
              >
                主流程
              </button>
              <ChevronRight className="text-muted-foreground/50 h-3 w-3" />
              <div className="flex items-center gap-1.5 text-xs font-semibold text-violet-700">
                <Layers className="h-3 w-3" />
                {activeSubflowLabel}
              </div>
              <button
                type="button"
                onClick={handleExitSubflow}
                className="ml-2 rounded-md border border-violet-200 bg-violet-50 px-2 py-0.5 text-[10px] font-medium text-violet-600 transition-colors hover:bg-violet-100"
              >
                ← 返回主流程
              </button>
            </div>
          )}

          {readOnly && !activeSubflowId && (
            <div className="bg-background/80 text-muted-foreground border-border pointer-events-none absolute top-4 left-4 rounded-md border px-3 py-1.5 text-xs font-medium backdrop-blur-sm">
              只读模式 — 工作流已锁定
            </div>
          )}
        </div>

        {/* Right: Property panel */}
        <div className="border-border bg-card w-72 shrink-0 overflow-y-auto border-l">
          {selectedNode ? (
            <div className="divide-border divide-y">
              <div className="bg-muted/30 flex items-start justify-between gap-2 px-4 py-3">
                <div className="min-w-0">
                  <div className="text-foreground truncate text-sm font-semibold">
                    {selectedNode.data.label || selectedNode.id}
                  </div>
                  <div className="text-muted-foreground mt-0.5 text-[10px]">
                    {NODE_TYPE_LABELS[selectedNode.type] ?? selectedNode.type}
                  </div>
                </div>
                <button
                  onClick={handleDeleteSelected}
                  className="text-muted-foreground/60 shrink-0 rounded-md p-1.5 transition-colors hover:bg-red-50 hover:text-red-500"
                  title="删除节点 (Delete)"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
              <div>{renderConfigPanel(selectedNode)}</div>
            </div>
          ) : (
            <div className="flex min-h-[200px] flex-col items-center justify-center gap-2 p-6 text-center">
              <div className="bg-muted/50 flex h-10 w-10 items-center justify-center rounded-full">
                <svg
                  className="text-muted-foreground/50 h-5 w-5"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122"
                  />
                </svg>
              </div>
              <div className="text-muted-foreground text-xs">
                点击画布中的节点
                <br />
                查看和编辑属性
              </div>
              <div className="text-muted-foreground/60 mt-1 text-[10px]">
                按 Delete 键可删除选中节点
              </div>
            </div>
          )}
        </div>

        {/* Built-in toolbar — only shown when NOT using external toolbar AND NOT readOnly */}
        {!hideToolbar && !readOnly && (
          <div className="bg-background/90 border-border absolute top-2 right-2 z-10 flex gap-1.5 rounded-lg border p-1.5 shadow-sm backdrop-blur-sm">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="border-border bg-background focus:ring-primary/20 focus:border-primary/40 rounded-md border px-2.5 py-1 text-sm focus:ring-2 focus:outline-none"
              placeholder="工作流名称"
            />
            <button
              onClick={handleValidate}
              disabled={isValidating}
              className="bg-secondary text-secondary-foreground hover:bg-secondary/80 rounded-md px-2.5 py-1 text-xs font-medium transition-colors"
            >
              {isValidating ? "校验中..." : "校验"}
            </button>
            {!onSaveTemplateProp && (
              <button
                onClick={handleSaveTemplate}
                disabled={saving}
                className="bg-muted text-muted-foreground hover:bg-muted/80 rounded-md px-2.5 py-1 text-xs font-medium transition-colors"
              >
                存为模板
              </button>
            )}
            <button
              onClick={handleSave}
              disabled={saving}
              className="bg-primary text-primary-foreground hover:bg-primary/90 rounded-md px-2.5 py-1 text-xs font-medium transition-colors"
            >
              {saving ? "保存中..." : "保存"}
            </button>
          </div>
        )}

        {/* Validation result overlay */}
        {validationResult && (
          <div
            className={`absolute right-72 bottom-3 left-52 z-10 mx-4 max-w-sm rounded-lg border p-3 text-sm shadow-lg ${
              validationResult.valid
                ? "border-green-200 bg-green-50"
                : "border-red-200 bg-red-50"
            }`}
          >
            <div className="flex items-center gap-1.5 font-semibold">
              <span>{validationResult.valid ? "✓" : "✗"}</span>
              {validationResult.valid ? "校验通过" : "校验失败"}
            </div>
            {validationResult.errors.map((e, i) => (
              <div key={i} className="mt-1 text-xs text-red-600">
                {e}
              </div>
            ))}
            {validationResult.warnings.map((w, i) => (
              <div key={i} className="mt-1 text-xs text-amber-600">
                {w}
              </div>
            ))}
          </div>
        )}
      </div>
    </ReactFlowProvider>
  );
});
