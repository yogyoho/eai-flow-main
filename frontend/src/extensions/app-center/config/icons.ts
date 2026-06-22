import {
  BookOpen,
  Bot,
  ClipboardList,
  Factory,
  FileOutput,
  FileText,
  FolderCheck,
  LayoutDashboard,
  PackageSearch,
  Settings2,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

/** Maps DB-stored icon_name strings to Lucide React components. */
export const ICON_MAP: Record<string, LucideIcon> = {
  "layout-dashboard": LayoutDashboard,
  bot: Bot,
  "clipboard-list": ClipboardList,
  "folder-check": FolderCheck,
  factory: Factory,
  "book-open": BookOpen,
  "file-output": FileOutput,
  "package-search": PackageSearch,
  "settings-2": Settings2,
  "file-text": FileText,
};

/** Fallback icon when icon_name is unknown. */
export const DEFAULT_ICON = LayoutDashboard;

/** Resolve an icon name to a Lucide component, with fallback. */
export function resolveIcon(iconName: string): LucideIcon {
  return ICON_MAP[iconName] ?? DEFAULT_ICON;
}
