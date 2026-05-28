"use client";

import { Check, ChevronDown, GripVertical, Plus, Sparkles, Trash2, UserPlus, X } from "lucide-react";
import { useCallback, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

interface FlowNode {
  id: string;
  title: string;
  description: string;
  type: "auto" | "single" | "countersign" | "majority";
  approvers: { id: string; name: string }[];
  returnRule: string;
  color: "gray" | "blue" | "yellow" | "green";
}

const DEFAULT_NODES: FlowNode[] = [
  { id: "n1", title: "编辑提交", description: "编辑完成并提交审核", type: "auto", approvers: [], returnRule: "", color: "gray" },
  { id: "n2", title: "审核", description: "单人审核", type: "single", approvers: [{ id: "u2", name: "王工" }], returnRule: "prev", color: "blue" },
  { id: "n3", title: "批准", description: "会签：李主任、赵主任", type: "countersign", approvers: [{ id: "u3", name: "李主任" }, { id: "u4", name: "赵主任" }], returnRule: "prev", color: "yellow" },
  { id: "n4", title: "定稿完成", description: "自动定稿", type: "auto", approvers: [], returnRule: "", color: "green" },
];

const NODE_BORDER_COLORS: Record<string, string> = {
  gray: "border-[#E2E8F0]",
  blue: "border-[#0746FF]",
  yellow: "border-[#F59E0B]",
  green: "border-[#10B981]",
};

interface ApprovalFlowEditorProps {
  onSave?: (nodes: FlowNode[]) => void;
}

export function ApprovalFlowEditor({ onSave }: ApprovalFlowEditorProps) {
  const [nodes, setNodes] = useState<FlowNode[]>(DEFAULT_NODES);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selectedNode = nodes.find((n) => n.id === selectedId) ?? null;

  const addNode = useCallback(() => {
    const id = `n${Date.now()}`;
    setNodes((prev) => [
      ...prev.slice(0, -1),
      { id, title: "新节点", description: "配置审批节点", type: "single", approvers: [], returnRule: "prev", color: "blue" },
      ...prev.slice(-1),
    ]);
    setSelectedId(id);
  }, []);

  const updateNode = useCallback((id: string, updates: Partial<FlowNode>) => {
    setNodes((prev) => prev.map((n) => (n.id === id ? { ...n, ...updates } : n)));
  }, []);

  const removeNode = useCallback(
    (id: string) => {
      setNodes((prev) => prev.filter((n) => n.id !== id));
      if (selectedId === id) setSelectedId(null);
    },
    [selectedId],
  );

  const handleSave = useCallback(() => {
    onSave?.(nodes);
  }, [nodes, onSave]);

  return (
    <div className="flex h-full">
      {/* Left: Flow canvas */}
      <div className="flex-1 overflow-y-auto pt-2 pb-10">
        <div className="mb-4 flex items-center justify-between px-6">
          <h3 className="text-[13px] font-semibold text-[#0F172A]">审批流程节点</h3>
          <span className="text-xs text-[#475569]">拖拽节点调整顺序</span>
        </div>

        <div className="flex flex-col items-center gap-0">
          {nodes.map((node, idx) => (
            <div key={node.id} className="flex flex-col items-center">
              {/* Connector line */}
              {idx > 0 && <div className="h-6 w-px bg-[#E2E8F0]" />}

              {/* Node card */}
              <button
                onClick={() => setSelectedId(node.id)}
                className={cn(
                  "flex w-full max-w-[520px] items-center gap-3 rounded-[8px] border-2 bg-white px-4 py-3 text-left transition-colors hover:bg-[#F9FAFB]",
                  NODE_BORDER_COLORS[node.color],
                  selectedId === node.id && "ring-2 ring-[#0746FF]/20",
                )}
              >
                <GripVertical className="h-4 w-4 shrink-0 text-[#94A3B8]" />
                <div className="min-w-0 flex-1">
                  <p className="text-[13px] font-semibold text-[#0F172A]">{node.title}</p>
                  <p className="text-[12px] text-[#475569]">{node.description}</p>
                </div>
                {node.type === "auto" ? (
                  <Sparkles className="h-4 w-4 shrink-0 text-[#94A3B8]" />
                ) : (
                  <span className="shrink-0 text-[12px] text-[#475569]">
                    {node.approvers.map((a) => a.name).join("、")}
                  </span>
                )}
              </button>
            </div>
          ))}

          {/* Add node button */}
          <div className="flex flex-col items-center">
            <div className="h-6 w-px bg-[#E2E8F0]" />
            <button
              onClick={addNode}
              className="flex w-full max-w-[520px] items-center justify-center gap-2 rounded-[8px] border-2 border-dashed border-[#E2E8F0] py-3 text-[13px] text-[#94A3B8] transition-colors hover:border-[#0746FF]/50 hover:text-[#0746FF]"
            >
              <Plus className="h-4 w-4" />
              添加审批节点
            </button>
          </div>
        </div>
      </div>

      {/* Right: Config panel (340px) */}
      <div className="w-[340px] shrink-0 overflow-y-auto border-l border-[#E2E8F0] bg-white p-5">
        {selectedNode ? (
          <div className="space-y-5">
            <h4 className="text-[13px] font-semibold text-[#0F172A]">节点配置</h4>

            {/* Node name */}
            <div>
              <label className="mb-1.5 block text-[12px] text-[#475569]">节点名称</label>
              <Input
                value={selectedNode.title}
                onChange={(e) => updateNode(selectedNode.id, { title: e.target.value })}
                className="h-[34px] rounded-[22px] border-[#E2E8F0] text-[13px]"
              />
            </div>

            {/* Approval type */}
            <div>
              <label className="mb-1.5 block text-[12px] text-[#475569]">审批方式</label>
              <div className="space-y-2.5">
                {[
                  { value: "single", label: "单人审核" },
                  { value: "countersign", label: "会签" },
                  { value: "majority", label: "多数通过" },
                ].map((opt) => (
                  <label key={opt.value} className="flex items-center gap-2 text-[13px] text-[#0F172A]">
                    <div
                      className={cn(
                        "flex h-4 w-4 items-center justify-center rounded-full border-2",
                        selectedNode.type === opt.value ? "border-[#0746FF]" : "border-[#CBD5E1]",
                      )}
                    >
                      {selectedNode.type === opt.value && <div className="h-2 w-2 rounded-full bg-[#0746FF]" />}
                    </div>
                    {opt.label}
                  </label>
                ))}
              </div>
            </div>

            {/* Approvers */}
            {selectedNode.type !== "auto" && (
              <div>
                <label className="mb-1.5 block text-[12px] text-[#475569]">审批人</label>
                <div className="space-y-2">
                  {selectedNode.approvers.map((approver) => (
                    <div key={approver.id} className="flex items-center gap-2 rounded-[8px] border border-[#E2E8F0] px-3 py-1.5">
                      <div className="flex h-6 w-6 items-center justify-center rounded-full bg-[#0746FF] text-[10px] font-medium text-white">
                        {approver.name[0]}
                      </div>
                      <span className="flex-1 text-[13px] text-[#0F172A]">{approver.name}</span>
                      <button
                        onClick={() => updateNode(selectedNode.id, { approvers: selectedNode.approvers.filter((a) => a.id !== approver.id) })}
                        className="text-[#94A3B8] hover:text-[#EF4444]"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ))}
                  <Button variant="outline" size="sm" className="w-full rounded-[8px] border-dashed border-[#E2E8F0] text-[12px] text-[#475569]">
                    <UserPlus className="mr-1.5 h-3.5 w-3.5" />
                    添加审批人
                  </Button>
                </div>
              </div>
            )}

            {/* Return rule */}
            {selectedNode.type !== "auto" && (
              <div>
                <label className="mb-1.5 block text-[12px] text-[#475569]">退回规则</label>
                <div className="relative">
                  <select
                    value={selectedNode.returnRule}
                    onChange={(e) => updateNode(selectedNode.id, { returnRule: e.target.value })}
                    className="h-[34px] w-full rounded-[8px] border border-[#E2E8F0] bg-white px-3 text-[13px] text-[#0F172A] appearance-none"
                  >
                    <option value="prev">退回至上一节点</option>
                    <option value="start">退回至开始节点</option>
                    <option value="specific">退回至指定节点</option>
                  </select>
                  <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-4 w-4 -translate-y-1/2 text-[#94A3B8]" />
                </div>
              </div>
            )}

            {/* Actions */}
            <div className="flex items-center gap-2 pt-2">
              {selectedNode.type !== "auto" && (
                <Button
                  variant="outline"
                  size="sm"
                  className="border-[#FEE2E2] text-[#EF4444] hover:bg-[#FEF2F2]"
                  onClick={() => removeNode(selectedNode.id)}
                >
                  <Trash2 className="mr-1 h-3.5 w-3.5" />
                  删除节点
                </Button>
              )}
              <Button size="sm" className="ml-auto rounded-[8px] bg-[#0746FF] hover:bg-[#063CD6]" onClick={handleSave}>
                应用
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex h-full items-center justify-center text-[13px] text-[#94A3B8]">点击节点查看配置</div>
        )}
      </div>
    </div>
  );
}
