"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef } from "react";

import {
  openSettingsDialog,
  type SettingsSection,
  useSettingsDialog,
} from "./settings";

// EAI-CUSTOM (upstream-sync 2026-10-16): fused upstream's exhaustive-Record
// whitelist with EAI's narrowed deep-link policy (appearance/about tabs were
// removed from the settings dialog; see commit c9b3af55a). The value type is
// `boolean` instead of upstream's literal `true` so every SettingsSection
// still needs a compiler-enforced entry, while non-whitelisted sections are
// an explicit `false` instead of silently missing.
const SETTINGS_SECTIONS: Record<SettingsSection, boolean> = {
  // Deep-link reachable (EAI whitelist).
  models: true,
  users: true, // upstream #6641 admin user management
  account: true,
  channels: true,
  memory: true,
  subagents: true,
  notification: true,
  // Deliberately NOT deep-link reachable (EAI narrowing / EAI-CUSTOM tabs).
  wechat: false,
  appearance: false,
  skills: false,
  about: false,
  integrations: false,
};

function asSettingsSection(value: string | null): SettingsSection | null {
  if (!value) return null;
  // `=== true` rejects inherited keys ("toString" in obj is true) that both
  // `in` and bare indexing would admit.
  return SETTINGS_SECTIONS[value as SettingsSection] === true
    ? (value as SettingsSection)
    : null;
}

/**
 * Bridges the `?settings=<section>` query param to the shared settings dialog
 * store. It does not mount its own dialog — a single {@link SettingsDialogHost}
 * renders the one dialog — so a deep link can never race a second dialog opened
 * from the nav menu or command palette.
 */
export function WorkspaceSettingsDeepLink() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { open } = useSettingsDialog();
  const openedFromDeepLinkRef = useRef(false);

  useEffect(() => {
    const nextSection = asSettingsSection(searchParams.get("settings"));
    if (nextSection) {
      openedFromDeepLinkRef.current = true;
      openSettingsDialog(nextSection);
    }
  }, [searchParams]);

  useEffect(() => {
    if (open || !openedFromDeepLinkRef.current) {
      return;
    }
    openedFromDeepLinkRef.current = false;
    if (searchParams.has("settings")) {
      const next = new URLSearchParams(searchParams);
      next.delete("settings");
      const suffix = next.toString();
      router.replace(suffix ? `${pathname}?${suffix}` : pathname, {
        scroll: false,
      });
    }
  }, [open, pathname, router, searchParams]);

  return null;
}
