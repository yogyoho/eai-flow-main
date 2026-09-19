"use client";

import {
  BellIcon,
  BrainIcon,
  CableIcon,
  MessageCircleIcon,
  SparklesIcon,
  UsersRoundIcon,
  UserIcon,
} from "lucide-react";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useI18n } from "@/core/i18n/hooks";
import { cn } from "@/lib/utils";

// EAI-CUSTOM: 对齐上游分包纪律 —— 每个 section page 一个懒加载 chunk
// (上游 #5468 缩减后 7 个；EAI 追加 skills/wechat 两个扩展懒加载项，共 9 个)。
// 打开设置只下载当前激活 section 的代码，而不是全部 9 页。
function SettingsPageLoading() {
  return (
    <p role="status" className="text-muted-foreground py-8 text-center text-sm">
      Loading…
    </p>
  );
}

const AccountSettingsPage = dynamic(
  () =>
    import("./account-settings-page").then(
      (module) => module.AccountSettingsPage,
    ),
  { loading: SettingsPageLoading },
);
const ChannelsSettingsPage = dynamic(
  () =>
    import("./channels-settings-page").then(
      (module) => module.ChannelsSettingsPage,
    ),
  { loading: SettingsPageLoading },
);
const MemorySettingsPage = dynamic(
  () =>
    import("./memory-settings-page").then(
      (module) => module.MemorySettingsPage,
    ),
  { loading: SettingsPageLoading },
);
const NotificationSettingsPage = dynamic(
  () =>
    import("./notification-settings-page").then(
      (module) => module.NotificationSettingsPage,
    ),
  { loading: SettingsPageLoading },
);
// EAI-CUSTOM: legacy skill/extension management page. Upstream #5468 moved
// stock skills to the capability center (/workspace/capabilities) and deleted
// this page; EAI keeps it for the "扩展" (legacy extensions) management tab and
// mounts it below as a settings section.
const SkillSettingsPage = dynamic(
  () =>
    import("./skill-settings-page").then((module) => module.SkillSettingsPage),
  { loading: SettingsPageLoading },
);
const SubagentSettingsPage = dynamic(
  () =>
    import("./subagent-settings-page").then(
      (module) => module.SubagentSettingsPage,
    ),
  { loading: SettingsPageLoading },
);
// EAI-CUSTOM (upstream-sync 2026-08-26): EAI's nav intentionally dropped the
// About section back then. Upstream #5468 restored About as a first-class
// settings section and this fused dialog adopts it, so the dynamic import is
// live code again (previously dead code here).
// EAI-CUSTOM: WeChat channel settings page
const WechatSettingsPage = dynamic(
  () =>
    import("./wechat-settings-page").then(
      (module) => module.WechatSettingsPage,
    ),
  { loading: SettingsPageLoading },
);

export type SettingsSection =
  | "account"
  | "wechat" // EAI-CUSTOM: WeChat channel section (wechat-settings-page)
  | "appearance"
  | "channels"
  | "memory"
  | "subagents"
  | "skills" // EAI-CUSTOM: legacy skills/extension management (skill-settings-page)
  | "notification"
  | "about"
  // EAI-CUSTOM (upstream-sync 2026-08-26): kept in the union so shared
  // (upstream) code compiling against EAI's section list stays valid; the
  // integrations page itself moved to the capability center (#5468).
  | "integrations";

type SettingsDialogProps = React.ComponentProps<typeof Dialog> & {
  defaultSection?: SettingsSection;
};

export function SettingsDialog(props: SettingsDialogProps) {
  const { defaultSection = "account", ...dialogProps } = props;
  const { t } = useI18n();
  const [activeSection, setActiveSection] =
    useState<SettingsSection>(defaultSection);

  useEffect(() => {
    // When opening the dialog, ensure the active section follows the caller's intent.
    // This allows triggers like "About" to open the dialog directly on that page.
    if (dialogProps.open) {
      setActiveSection(defaultSection);
    }
  }, [defaultSection, dialogProps.open]);

  const sections = useMemo(
    () => [
      {
        id: "account",
        label: t.settings.sections.account,
        icon: UserIcon,
      },
      {
        id: "wechat", // EAI-CUSTOM
        label: "微信",
        icon: MessageCircleIcon,
      },
      {
        id: "notification",
        label: t.settings.sections.notification,
        icon: BellIcon,
      },
      {
        id: "channels",
        label: t.settings.sections.channels,
        icon: CableIcon,
      },
      {
        id: "memory",
        label: t.settings.sections.memory,
        icon: BrainIcon,
      },
      {
        id: "subagents",
        label: t.settings.sections.subagents,
        icon: UsersRoundIcon,
      },
      // EAI-CUSTOM: legacy skills/extension entry — upstream #5468 moved stock
      // skills to /workspace/capabilities, but EAI keeps this settings tab as
      // the entry to skill-settings-page. The label reuses
      // t.capabilities.skills because the upstream i18n sync removed
      // settings.sections.skills.
      {
        id: "skills",
        label: t.capabilities.skills,
        icon: SparklesIcon,
      },
    ],
    [
      t.settings.sections.account,
      t.settings.sections.channels,
      t.settings.sections.memory,
      t.settings.sections.subagents,
      t.settings.sections.notification,
      t.capabilities.skills,
    ],
  );
  return (
    <Dialog
      {...dialogProps}
      onOpenChange={(open) => props.onOpenChange?.(open)}
    >
      <DialogContent
        className="flex h-[75vh] max-h-[calc(100vh-2rem)] flex-col sm:max-w-5xl md:max-w-6xl"
        aria-describedby={undefined}
      >
        <DialogHeader className="gap-1">
          <DialogTitle>{t.settings.title}</DialogTitle>
          <p className="text-muted-foreground text-sm">
            {t.settings.description}
          </p>
        </DialogHeader>
        <div className="grid min-h-0 flex-1 gap-4 md:grid-cols-[220px_minmax(0,1fr)]">
          <nav className="bg-sidebar min-h-0 overflow-y-auto rounded-lg border p-2">
            <ul className="space-y-1 pr-1">
              {sections.map(({ id, label, icon: Icon }) => {
                const active = activeSection === id;
                return (
                  <li key={id}>
                    <button
                      type="button"
                      onClick={() => setActiveSection(id as SettingsSection)}
                      className={cn(
                        "flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                        active
                          ? "bg-primary text-primary-foreground shadow-sm"
                          : "text-muted-foreground hover:bg-muted hover:text-foreground",
                      )}
                    >
                      <Icon className="size-4" />
                      <span>{label}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </nav>
          <ScrollArea className="h-full min-h-0 rounded-lg border">
            <div className="space-y-8 p-6">
              {activeSection === "account" && <AccountSettingsPage />}
              {activeSection === "wechat" && <WechatSettingsPage />}
              {activeSection === "memory" && <MemorySettingsPage />}
              {activeSection === "subagents" && <SubagentSettingsPage />}
              {activeSection === "skills" && (
                <SkillSettingsPage
                  onClose={() => props.onOpenChange?.(false)}
                />
              )}
              {activeSection === "notification" && <NotificationSettingsPage />}
              {activeSection === "channels" && <ChannelsSettingsPage />}
            </div>
          </ScrollArea>
        </div>
      </DialogContent>
    </Dialog>
  );
}
