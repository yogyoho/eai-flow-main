"use client";

import { BookOpen } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  MEMBER_ROLE_LABELS,
  type MemberRole,
  type ProjectChapter,
  type ProjectMember,
} from "@/extensions/project/types";
import { groupByRole } from "@/extensions/project/utils";

// EAI-CUSTOM: 按职责(角色)分工看板(ADR 2026-08-10)。
// v1 = 角色分组的花名册 + 职责说明,不做自动章节重指派(spec §10 β)。

const ROLE_ORDER: MemberRole[] = ["writer", "reviewer", "approver", "phase_lead", "owner"];
const ROLE_DUTY: Record<MemberRole, string> = {
  writer: "改写初稿内容",
  reviewer: "审校章节质量",
  approver: "审批定稿",
  phase_lead: "牵头推进",
  owner: "项目负责",
};

interface RoleBoardProps {
  members: ProjectMember[];
  chapters: ProjectChapter[];
  onEdit: (chapterId: string) => void;
}

export function RoleBoard({ members, chapters: _chapters, onEdit: _onEdit }: RoleBoardProps) {
  const groups = groupByRole(members);
  const presentRoles = ROLE_ORDER.filter((r) => (groups[r]?.length ?? 0) > 0);

  if (presentRoles.length === 0) {
    return (
      <div className="px-5 pb-6 pt-4 flex flex-col items-center text-center">
        <BookOpen className="h-8 w-8 text-muted-foreground/30 mb-2" />
        <p className="text-sm text-muted-foreground">尚无项目成员</p>
        <p className="text-xs text-muted-foreground/60 mt-1">按职责分工需先添加成员并分配角色</p>
      </div>
    );
  }

  return (
    <div className="px-5 pb-4 pt-2 grid grid-cols-1 sm:grid-cols-2 gap-3 max-h-[480px] overflow-y-auto pr-1 cyber-scroll">
      {presentRoles.map((role) => (
        <div key={role} className="rounded-lg border border-border/60 p-3">
          <div className="flex items-center justify-between mb-2">
            <Badge variant="secondary" className="text-[10px] font-normal">
              {MEMBER_ROLE_LABELS[role] ?? role}
            </Badge>
            <span className="text-[11px] text-muted-foreground">{ROLE_DUTY[role]}</span>
          </div>
          <div className="space-y-1.5">
            {(groups[role] ?? []).map((m) => (
              <div key={m.id} className="flex items-center gap-2">
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[10px] font-medium text-primary">
                  {(m.username ?? "?").charAt(0).toUpperCase()}
                </div>
                <span className="text-sm text-foreground truncate">{m.username}</span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
