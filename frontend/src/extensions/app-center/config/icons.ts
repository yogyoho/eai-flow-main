import {
  BookMarked,
  BookOpen,
  Bot,
  ClipboardList,
  Factory,
  FileOutput,
  FileText,
  FolderCheck,
  Gavel,
  LayoutDashboard,
  Map,
  PackageSearch,
  Settings2,
  Users,
  Workflow,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

/** Maps DB-stored icon_name strings to Lucide React components. */
export const ICON_MAP: Record<string, LucideIcon> = {
  "layout-dashboard": LayoutDashboard,
  map: Map,
  bot: Bot,
  "clipboard-list": ClipboardList,
  // EAI-CUSTOM (bug-3109 v4): 投标资料管理（app_definitions seed icon="book-marked"）
  "book-marked": BookMarked,
  "folder-check": FolderCheck,
  factory: Factory,
  "book-open": BookOpen,
  "file-output": FileOutput,
  "package-search": PackageSearch,
  "settings-2": Settings2,
  "file-text": FileText,
  users: Users,
  workflow: Workflow,
  gavel: Gavel,
};

/** Fallback icon when icon_name is unknown. */
export const DEFAULT_ICON = LayoutDashboard;

/** Resolve an icon name to a Lucide component, with fallback. */
export function resolveIcon(iconName: string): LucideIcon {
  return ICON_MAP[iconName] ?? DEFAULT_ICON;
}
