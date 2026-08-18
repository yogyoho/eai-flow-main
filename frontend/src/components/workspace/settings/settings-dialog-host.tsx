"use client";

// EAI-CUSTOM: 对齐上游 lazy-panels 分包纪律 (2026-08-19)。EAI 此前由
// workspace-nav-menu 用本地 useState 直接静态挂载 <SettingsDialog>，导致
// dialog + 7 个 section page 全部打进 workspace 首屏 chunk，且 command
// palette / deep-link 走 store 的入口实际打不开 dialog（store 无人消费）。
// 现恢复上游形态：host 统一挂载 + dynamic() 懒加载 + 未打开时返回 null。
import dynamic from "next/dynamic";

import {
  setSettingsDialogOpen,
  useSettingsDialog,
} from "./settings-dialog-store";

const SettingsDialog = dynamic(
  () => import("./settings-dialog").then((module) => module.SettingsDialog),
  {
    ssr: false,
    loading: () => (
      <div className="bg-background/80 fixed inset-0 z-50 grid place-items-center backdrop-blur-sm">
        <p role="status" className="text-muted-foreground text-sm">
          Loading settings…
        </p>
      </div>
    ),
  },
);

/**
 * The single application-wide Settings dialog instance.
 *
 * Mounted once at the workspace root; every entry point (nav menu, command
 * palette, deep link) opens it through the shared store rather than mounting
 * its own dialog.
 */
export function SettingsDialogHost() {
  const { open, section } = useSettingsDialog();
  if (!open) return null;
  return (
    <SettingsDialog
      open={open}
      onOpenChange={setSettingsDialogOpen}
      defaultSection={section}
    />
  );
}
