"use client";

// Collab Workspace — 成员面板（人类/数字员工）
// EAI-CUSTOM: 全新模块。UI 对齐 cyber 主题。

import { Plus, Trash2, Bot, User } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";

import { workspaceApi } from "../api";
import type { CollabMember } from "../types";

const ROLE_LABEL: Record<string, string> = {
  owner: "Owner",
  editor: "编辑",
  reviewer: "审核",
  coordinator: "协调",
};

interface MembersPaneProps {
  projectId: string;
  projectName: string;
  onRefresh: () => void;
}

export function MembersPane({ projectId, projectName }: MembersPaneProps) {
  const [members, setMembers] = useState<CollabMember[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [memberType, setMemberType] = useState<"human" | "agent">("agent");
  const [agentName, setAgentName] = useState("");
  const [userId, setUserId] = useState("");
  const [role, setRole] = useState("editor");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const data = await workspaceApi.listMembers(projectId);
      setMembers(data);
    } catch {
      toast.error("加载成员失败");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  const addMember = async () => {
    try {
      if (memberType === "agent" && !agentName.trim()) {
        toast.error("请输入 agent_name");
        return;
      }
      if (memberType === "human" && !userId.trim()) {
        toast.error("请输入 user_id");
        return;
      }
      await workspaceApi.addMember(projectId, {
        memberType,
        agentName: memberType === "agent" ? agentName.trim() : undefined,
        userId: memberType === "human" ? userId.trim() : undefined,
        role,
      });
      toast.success("成员已添加");
      setShowAdd(false);
      setAgentName("");
      setUserId("");
      void load();
    } catch {
      toast.error("添加失败");
    }
  };

  const removeMember = async (memberId: string) => {
    try {
      await workspaceApi.removeMember(projectId, memberId);
      toast.success("成员已移除");
      void load();
    } catch {
      toast.error("移除失败");
    }
  };

  if (loading) {
    return (
      <div className="text-muted-foreground flex h-40 items-center justify-center text-sm">
        加载中...
      </div>
    );
  }

  return (
    <div className="max-w-2xl p-6">
      <div className="mb-4 flex items-center justify-between">
        <h2
          className="text-sm font-bold"
          style={{ color: "var(--cyber-text-main)" }}
        >
          项目成员 · {projectName}
        </h2>
        <Button size="sm" onClick={() => setShowAdd((v) => !v)}>
          <Plus className="mr-1 h-4 w-4" /> 添加成员
        </Button>
      </div>

      {showAdd && (
        <div
          className="mb-4 flex flex-col gap-3 rounded-xl border p-4"
          style={{
            background: "var(--cyber-bg-secondary)",
            borderColor: "var(--cyber-border-muted)",
          }}
        >
          <div className="flex gap-2">
            {(["agent", "human"] as const).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setMemberType(t)}
                className={`flex-1 cursor-pointer rounded-lg border px-3 py-2 text-xs font-bold transition ${
                  memberType === t
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border text-muted-foreground"
                }`}
              >
                {t === "agent" ? "数字员工" : "真人"}
              </button>
            ))}
          </div>
          {memberType === "agent" ? (
            <input
              className="border-input bg-background flex h-9 w-full rounded-md border px-3 py-1 text-sm"
              placeholder="agent_name（如 writing-assistant）"
              value={agentName}
              onChange={(e) => setAgentName(e.target.value)}
            />
          ) : (
            <input
              className="border-input bg-background flex h-9 w-full rounded-md border px-3 py-1 text-sm"
              placeholder="user_id (UUID)"
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
            />
          )}
          <div className="flex gap-2">
            {(["editor", "reviewer", "coordinator"] as const).map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => setRole(r)}
                className={`flex-1 cursor-pointer rounded-lg border px-3 py-1.5 text-xs font-bold transition ${
                  role === r
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border text-muted-foreground"
                }`}
              >
                {ROLE_LABEL[r]}
              </button>
            ))}
          </div>
          <Button size="sm" onClick={addMember}>
            添加
          </Button>
        </div>
      )}

      <div className="flex flex-col gap-2">
        {members.map((m) => (
          <div
            key={m.id}
            className="flex items-center justify-between rounded-xl border p-3"
            style={{
              background: "var(--cyber-bg-secondary)",
              borderColor: "var(--cyber-border-muted)",
            }}
          >
            <div className="flex items-center gap-3">
              <span
                className={`rounded-lg p-1.5 ${m.memberType === "agent" ? "bg-purple-500/10" : "bg-cyan-500/10"}`}
              >
                {m.memberType === "agent" ? (
                  <Bot className="h-4 w-4 text-purple-400" />
                ) : (
                  <User className="h-4 w-4 text-cyan-400" />
                )}
              </span>
              <div>
                <p
                  className="text-sm font-bold"
                  style={{ color: "var(--cyber-text-main)" }}
                >
                  {m.memberType === "agent" ? m.agentName : m.userId}
                </p>
                <p className="text-muted-foreground font-mono text-[11px]">
                  {ROLE_LABEL[m.role] ?? m.role}
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => removeMember(m.id)}
              className="text-muted-foreground cursor-pointer rounded-lg p-1.5 hover:text-red-400"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
        {members.length === 0 && (
          <div className="text-muted-foreground p-6 text-center text-xs">
            暂无成员
          </div>
        )}
      </div>
    </div>
  );
}
