"use client";

import { Compass, SearchX } from "lucide-react";

import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";

interface EmptyStateProps {
  variant: "no-results" | "no-apps";
}

/**
 * 空状态 —— 区分"搜索无结果"与"无可用应用（权限）"。
 */
export function EmptyState({ variant }: EmptyStateProps) {
  if (variant === "no-apps") {
    return (
      <Empty className="py-16">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <Compass />
          </EmptyMedia>
          <EmptyTitle>暂无可用应用</EmptyTitle>
          <EmptyDescription>
            当前账号未开通任何应用权限，请联系管理员分配角色或授权模块。
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  return (
    <Empty className="py-16">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <SearchX />
        </EmptyMedia>
        <EmptyTitle>未找到匹配的应用</EmptyTitle>
        <EmptyDescription>
          试试更换关键词，或清除筛选条件浏览全部应用。
        </EmptyDescription>
      </EmptyHeader>
    </Empty>
  );
}
