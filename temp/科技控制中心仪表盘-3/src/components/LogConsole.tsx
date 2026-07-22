/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React from "react";
import { Bell, Check, ExternalLink, ShieldAlert, Cpu, Activity } from "lucide-react";
import { NotificationLog } from "../types.js";
import { motion, AnimatePresence } from "motion/react";

interface LogConsoleProps {
  notifications: NotificationLog[];
  onMarkAllRead: () => void;
  onMarkRead: (id: string) => void;
}

export default function LogConsole({
  notifications,
  onMarkAllRead,
  onMarkRead,
}: LogConsoleProps) {
  const unreadCount = notifications.filter(n => n.unread).length;

  const getCategoryTheme = (cat: NotificationLog["category"]) => {
    switch (cat) {
      case "security":
        return {
          border: "border-red-500/20 bg-red-500/5 hover:border-red-500/40",
          icon: <ShieldAlert className="w-4 h-4 text-red-500" />,
          accent: "text-red-500",
          glow: "shadow-[0_0_8px_rgba(239,68,68,0.06)]"
        };
      case "workflow":
        return {
          border: "border-purple-500/20 bg-purple-500/5 hover:border-purple-500/40",
          icon: <Activity className="w-4 h-4 text-purple-500 animate-pulse" />,
          accent: "text-purple-500",
          glow: "shadow-[0_0_8px_rgba(139,92,246,0.06)]"
        };
      default:
        return {
          border: "border-cyan-500/20 bg-cyan-500/5 hover:border-cyan-500/40",
          icon: <Cpu className="w-4 h-4 text-cyan-500" />,
          accent: "text-cyan-500",
          glow: "shadow-[0_0_8px_rgba(6,182,212,0.06)]"
        };
    }
  };

  return (
    <div className="themed-card rounded-xl p-4 md:p-5 relative flex flex-col h-full overflow-hidden">
      {/* Decorative cyber corner */}
      <div className="absolute top-0 left-0 w-2 h-2 bg-[var(--border-color)]" />

      {/* Header */}
      <div className="flex items-center justify-between border-b border-[var(--border-color-muted)] pb-3 mb-4">
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-cyan-500/10 border border-cyan-500/20 text-cyan-500 rounded-md relative animate-fade-in">
            <Bell className="w-4 h-4" />
            {unreadCount > 0 && (
              <span className="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-red-500 ring-2 ring-[var(--bg-secondary)] animate-ping" />
            )}
          </div>
          <h2 className="text-sm font-bold tracking-wider themed-text-primary uppercase font-cyber flex items-center gap-1.5">
            消息通知 <span className="text-xs font-normal text-slate-500">System Logs</span>
          </h2>
        </div>

        {/* Unread metrics and action */}
        <div className="flex items-center gap-2 text-xs">
          {unreadCount > 0 && (
            <span className="font-cyber font-bold text-red-500 animate-pulse bg-red-500/10 border border-red-500/20 px-1.5 py-0.5 rounded text-[10px]">
              {unreadCount}条未读
            </span>
          )}
          <button
            onClick={onMarkAllRead}
            className="text-xs text-cyan-600 dark:text-cyan-400 hover:text-cyan-555 font-sans hover:underline cursor-pointer"
          >
            全部已读
          </button>
        </div>
      </div>

      {/* Logs Scroll Matrix */}
      <div className="flex-1 overflow-y-auto max-h-[360px] pr-1.5 flex flex-col gap-2.5">
        <AnimatePresence initial={false} mode="popLayout">
          {notifications.length === 0 ? (
            <div className="text-center py-10 text-slate-500 text-xs italic font-cyber">
              &gt; LOG STREAM CLEARED // ZERO RECORDS RECORDED
            </div>
          ) : (
            notifications.map(notif => {
              const theme = getCategoryTheme(notif.category);
              return (
                <motion.div
                  key={notif.id}
                  layout
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, x: 20 }}
                  className={`p-3 rounded-lg border transition-all ${theme.border} ${theme.glow} ${
                    notif.unread ? "bg-slate-400/10 border-cyan-500/30" : "bg-slate-400/5 border-transparent"
                  } flex flex-col gap-1.5 group select-none`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-2 min-w-0">
                      {theme.icon}
                      <h4 className={`text-xs font-semibold truncate font-sans ${
                        notif.unread ? "text-[var(--text-main)]" : "text-slate-500 font-normal"
                      }`}>
                        {notif.title}
                      </h4>
                    </div>

                    {/* Action controls */}
                    <div className="flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                      {notif.unread && (
                        <button
                          onClick={() => onMarkRead(notif.id)}
                          className="p-1 rounded bg-[var(--bg-tertiary)] border border-[var(--border-color)] text-slate-500 hover:text-cyan-500 hover:border-cyan-500/30 transition-all cursor-pointer"
                          title="标记为已读"
                        >
                          <Check className="w-3 h-3" />
                        </button>
                      )}
                      {notif.actionUrl && (
                        <a
                          href={notif.actionUrl}
                          className="p-1 rounded bg-[var(--bg-tertiary)] border border-[var(--border-color)] text-slate-500 hover:text-cyan-500 transition-all cursor-pointer"
                          title="查看遥测源"
                        >
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      )}
                    </div>
                  </div>

                  {/* Description details */}
                  <p className="text-[11px] text-slate-505 dark:text-slate-400 px-6 leading-relaxed font-sans font-normal">
                    {notif.description}
                  </p>

                  {/* Metadata line */}
                  <div className="flex items-center justify-between px-6 text-[9px] font-cyber text-slate-500 mt-0.5">
                    <span>{notif.timestamp}</span>
                    <div className="flex items-center gap-2">
                      <span className="capitalize">{notif.category} Channel</span>
                      {notif.unread && (
                        <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse ml-1 inline-block" />
                      )}
                    </div>
                  </div>
                </motion.div>
              );
            })
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
