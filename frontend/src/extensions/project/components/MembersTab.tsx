"use client";

import { MemberList } from "@/extensions/project/components/MemberList";
import { type ReportProject } from "@/extensions/project/types";

interface MembersTabProps {
  project: ReportProject;
  onRefresh: () => void;
  canManage: boolean;
}

export function MembersTab({ project, onRefresh, canManage }: MembersTabProps) {
  return (
    <div className="p-5">
      <MemberList
        members={project.members ?? []}
        projectId={project.id}
        onUpdate={onRefresh}
        canManage={canManage}
      />
    </div>
  );
}
