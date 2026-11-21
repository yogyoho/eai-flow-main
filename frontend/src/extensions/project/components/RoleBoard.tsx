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

const ROLE_ORDER: MemberRole[] = [
  "writer",
  "reviewer",
  "approver",
  "phase_lead",
  "owner",
];
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

export function RoleBoard({
  members,
  chapters: _chapters,
  onEdit: _onEdit,
}: RoleBoardProps) {
  const groups = groupByRole(members);
  const presentRoles = ROLE_ORDER.filter((r) => (groups[r]?.length ?? 0) > 0);

  if (presentRoles.length === 0) {
    return (
      <div className="flex flex-col items-center px-5 pt-4 pb-6 text-center">
        <BookOpen className="text-muted-foreground/30 mb-2 h-8 w-8" />
        <p className="text-muted-foreground text-sm">尚无项目成员</p>
        <p className="text-muted-foreground/60 mt-1 text-xs">
          按职责分工需先添加成员并分配角色
        </p>
      </div>
    );
  }

  return (
    <div className="cyber-scroll grid max-h-[480px] grid-cols-1 gap-3 overflow-y-auto px-5 pt-2 pr-1 pb-4 sm:grid-cols-2">
      {presentRoles.map((role) => (
        <div key={role} className="border-border/60 rounded-lg border p-3">
          <div className="mb-2 flex items-center justify-between">
            <Badge variant="secondary" className="text-[10px] font-normal">
              {MEMBER_ROLE_LABELS[role] ?? role}
            </Badge>
            <span className="text-muted-foreground text-xs">
              {ROLE_DUTY[role]}
            </span>
          </div>
          <div className="space-y-1.5">
            {(groups[role] ?? []).map((m) => (
              <div key={m.id} className="flex items-center gap-2">
                <div className="bg-primary/10 text-primary flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] font-medium">
                  {(m.username ?? "?").charAt(0).toUpperCase()}
                </div>
                <span className="text-foreground truncate text-sm">
                  {m.username}
                </span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
