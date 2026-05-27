"use client";

import type { CollabUser } from "./useCollab";

interface OnlineUsersProps {
  users: CollabUser[];
  connected: boolean;
}

export function OnlineUsers({ users, connected }: OnlineUsersProps) {
  if (!connected && users.length === 0) return null;

  return (
    <div className="flex items-center gap-1">
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
    </div>
  );
}
