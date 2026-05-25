export interface TabConfig {
  id: string;
  label: string;
  icon: string;
  stages: number[];
  minPermission: string | null;
  defaultForRoles: string[];
}

export const TAB_REGISTRY: TabConfig[] = [
  {
    id: "my-workspace",
    label: "我的工作台",
    icon: "Target",
    stages: [3, 4, 5],
    minPermission: null,
    defaultForRoles: ["editor", "writer"],
  },
  {
    id: "dashboard",
    label: "仪表盘",
    icon: "BarChart3",
    stages: [2, 3, 4, 5, 6],
    minPermission: null,
    defaultForRoles: ["manager"],
  },
  {
    id: "kanban",
    label: "看板",
    icon: "Kanban",
    stages: [3, 4],
    minPermission: "chapter:view_all",
    defaultForRoles: ["reviewer", "approver"],
  },
  {
    id: "outline",
    label: "大纲",
    icon: "FileText",
    stages: [2, 3, 4],
    minPermission: "outline:view",
    defaultForRoles: [],
  },
  {
    id: "members",
    label: "成员",
    icon: "Users",
    stages: [2, 3, 4, 5, 6],
    minPermission: "member:list",
    defaultForRoles: [],
  },
  {
    id: "approval",
    label: "审核",
    icon: "CheckCircle",
    stages: [5],
    minPermission: "approval:view",
    defaultForRoles: [],
  },
  {
    id: "ai-tools",
    label: "AI工具",
    icon: "Bot",
    stages: [3, 4],
    minPermission: "ai:toolbox",
    defaultForRoles: [],
  },
];

export function getVisibleTabs(
  stage: number,
  permissions: string[],
  _role: string | null,
): TabConfig[] {
  return TAB_REGISTRY.filter((tab) => {
    if (!tab.stages.includes(stage)) return false;
    if (tab.minPermission && !permissions.includes(tab.minPermission)) return false;
    return true;
  });
}

export function getDefaultTab(
  stage: number,
  permissions: string[],
  role: string | null,
): string {
  const visible = getVisibleTabs(stage, permissions, role);
  if (!role) return "dashboard";

  const roleDefault = TAB_REGISTRY.find((t) => t.defaultForRoles.includes(role));
  if (roleDefault && visible.find((t) => t.id === roleDefault.id)) {
    return roleDefault.id;
  }

  return visible[0]?.id ?? "dashboard";
}
