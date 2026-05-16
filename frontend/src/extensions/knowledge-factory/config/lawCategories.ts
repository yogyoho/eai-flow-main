import {
  BookOpen,
  Factory,
  FileText,
  Globe,
  Ruler,
  Scale,
  Shield,
} from "lucide-react";

export type LawType =
  | "law"
  | "regulation"
  | "rule"
  | "national"
  | "industry"
  | "local"
  | "technical";

export interface LawCategory {
  icon: typeof Scale;
  name: string;
  code: LawType;
  color: string;
  bgColor: string;
  description: string;
  ragflowKbName: string;
}

export const LAW_CATEGORIES: LawCategory[] = [
  {
    icon: Scale,
    name: "法律",
    code: "law",
    color: "text-primary",
    bgColor: "bg-primary/10",
    description: "全国人大及常委会制定",
    ragflowKbName: "ragflow-laws-legal",
  },
  {
    icon: BookOpen,
    name: "行政法规",
    code: "regulation",
    color: "text-purple-500",
    bgColor: "bg-purple-500/10",
    description: "国务院制定",
    ragflowKbName: "ragflow-laws-legal",
  },
  {
    icon: FileText,
    name: "部门规章",
    code: "rule",
    color: "text-orange-500",
    bgColor: "bg-orange-500/10",
    description: "各部委（生态环境部等）",
    ragflowKbName: "ragflow-laws-legal",
  },
  {
    icon: Shield,
    name: "国家标准",
    code: "national",
    color: "text-red-500",
    bgColor: "bg-red-500/10",
    description: "GB系列（如GB 3095空气质量标准）",
    ragflowKbName: "ragflow-laws-standards",
  },
  {
    icon: Factory,
    name: "行业标准",
    code: "industry",
    color: "text-amber-500",
    bgColor: "bg-amber-500/10",
    description: "HJ、SY、NB等系列",
    ragflowKbName: "ragflow-laws-standards",
  },
  {
    icon: Globe,
    name: "地方标准",
    code: "local",
    color: "text-cyan-500",
    bgColor: "bg-cyan-500/10",
    description: "各省市地方标准",
    ragflowKbName: "ragflow-laws-standards",
  },
  {
    icon: Ruler,
    name: "技术规范",
    code: "technical",
    color: "text-green-500",
    bgColor: "bg-green-500/10",
    description: "环评技术导则、方法指南",
    ragflowKbName: "ragflow-laws-standards",
  },
];

export const LAW_TYPE_OPTIONS = LAW_CATEGORIES.map((cat) => ({
  value: cat.code,
  label: cat.name,
}));

export const LAW_STATUS_OPTIONS = [
  { value: "active", label: "现行有效" },
  { value: "deprecated", label: "已废止" },
  { value: "updating", label: "正在修订" },
];

export const SECTOR_OPTIONS = [
  { value: "all", label: "全部行业" },
  { value: "chemical", label: "化工" },
  { value: "coal", label: "煤炭" },
  { value: "power", label: "电力" },
  { value: "metallurgy", label: "冶金" },
  { value: "construction", label: "建材" },
  { value: "petroleum", label: "石油" },
  { value: "mining", label: "采矿" },
  { value: "其他", label: "其他" },
];

export function getCategoryByCode(code: LawType): LawCategory | undefined {
  return LAW_CATEGORIES.find((cat) => cat.code === code);
}

export function getCategoryName(code: LawType): string {
  return getCategoryByCode(code)?.name ?? code;
}

export function getCategoryColor(code: LawType): {
  color: string;
  bgColor: string;
} {
  const cat = getCategoryByCode(code);
  return {
    color: cat?.color ?? "text-muted-foreground",
    bgColor: cat?.bgColor ?? "bg-muted",
  };
}
