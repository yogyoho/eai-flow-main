"use client";

import { useEffect, useState } from "react";

import type { CollabUser } from "./useCollab";

interface OnlineUsersProps {
  users: CollabUser[];
  connected: boolean;
}

export function OnlineUsers({ users, connected }: OnlineUsersProps) {
  // EAI-CUSTOM (bug B10 协同写作链审计): 断连持续 >3s 才亮离线横幅——
  // 短暂重连抖动不闪红；恢复连接后自动消失。横幅浮于编辑器顶部（top bar 下方），
  // 提示内容此时不会落库，避免用户在断连状态下编辑而静默丢失。
  const [showOfflineBanner, setShowOfflineBanner] = useState(false);

  useEffect(() => {
    if (connected) {
      setShowOfflineBanner(false);
      return;
    }
    const timer = setTimeout(() => setShowOfflineBanner(true), 3000);
    return () => clearTimeout(timer);
  }, [connected]);

  if (!connected && users.length === 0 && !showOfflineBanner) return null;

  return (
    // relative 锚点：横幅 absolute 挂在本组件下方（编辑器顶部 bar 下缘），不挤占布局
    <div className="relative flex items-center gap-1">
      {users.map((user) => (
        <div
          key={user.clientId}
          className="w-7 h-7 rounded-full flex items-center justify-center text-xs text-white font-medium"
          style={{ backgroundColor: user.color }}
          title={user.name}
        >
          {user.name.charAt(0).toUpperCase()}
        </div>
      ))}
      {!connected && (
        <span className="text-xs text-muted-foreground ml-1">未连接</span>
      )}
      {showOfflineBanner && (
        <div
          role="alert"
          className="border-destructive/30 bg-destructive/10 text-destructive absolute top-full left-1/2 z-50 mt-2 flex -translate-x-1/2 items-center gap-2 rounded-md border px-3 py-1.5 text-xs whitespace-nowrap shadow-md"
        >
          协作服务未连接，内容不会保存
        </div>
      )}
    </div>
  );
}
