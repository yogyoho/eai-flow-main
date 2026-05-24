"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import type { ProjectMember } from "@/extensions/project/types";
import { MEMBER_ROLE_LABELS } from "@/extensions/project/types";
import { projectApi } from "@/extensions/project/api";
import { ChevronDown } from "lucide-react";
import { toast } from "sonner";

interface ChapterAssignDropdownProps {
  projectId: string;
  chapterId: string;
  members: ProjectMember[];
  currentAssignee: string | null;
  onAssigned: () => void;
}

export function ChapterAssignDropdown({
  projectId,
  chapterId,
  members,
  currentAssignee,
  onAssigned,
}: ChapterAssignDropdownProps) {
  const [open, setOpen] = useState(false);

  const handleAssign = async (userId: string) => {
    try {
      await projectApi.updateChapter(projectId, chapterId, { assignedTo: userId });
      setOpen(false);
      onAssigned();
    } catch {
      toast.error("分配失败");
    }
  };

  return (
    <div className="relative">
      <Button variant="outline" size="sm" className="h-7 text-xs gap-1" onClick={() => setOpen(!open)}>
        分配编写人
        <ChevronDown className="h-3 w-3" />
      </Button>
      {open && (
        <div className="absolute top-full left-0 mt-1 z-10 min-w-[160px] rounded-md border border-border bg-background shadow-md py-1">
          {members.map((m) => (
            <button
              key={m.userId}
              className="flex w-full items-center gap-2 px-3 py-1.5 text-sm hover:bg-muted text-left"
              onClick={() => handleAssign(m.userId)}
            >
              <span className="text-foreground">{m.username}</span>
              <span className="text-xs text-muted-foreground">{MEMBER_ROLE_LABELS[m.role]}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
