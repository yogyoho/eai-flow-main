"use client";

import {
  ArrowLeft,
  CalendarIcon,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  FileText,
  Loader2,
  Plus,
  Search,
  Sparkles,
  UserCircle,
  X,
} from "lucide-react";
import { useRouter } from "next/navigation";
import React, { useState, useCallback } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { projectApi } from "@/extensions/project/api";
import {
  MEMBER_ROLE_LABELS,
  REPORT_TYPE_LABELS,
  type MemberRole,
  type ReportType,
} from "@/extensions/project/types";
import { authFetch } from "@/extensions/api/client";
import { cn } from "@/lib/utils";

// ─── Types ──────────────────────────────────────────────────────────────────────

interface SelectOption {
  value: string;
  label: string;
}

type WizardStep = 1 | 2 | 3 | 4;

// ─── Constants ───────────────────────────────────────────────────────────────────

const STEPS: { step: WizardStep; key: string; label: string }[] = [
  { step: 1, key: "1", label: "基本信息" },
  { step: 2, key: "2", label: "选择模板" },
  { step: 3, key: "3", label: "组建团队" },
  { step: 4, key: "4", label: "确认创建" },
];

const REPORT_TYPE_OPTIONS: SelectOption[] = Object.entries(REPORT_TYPE_LABELS).map(
  ([value, label]) => ({ value, label }),
);

const REPORT_TYPE_TO_DOMAIN: Record<string, string[]> = {
  environmental_impact: ["environmental_impact", "environmental_impact_assessment", "environmental"],
  geological_survey: ["geological_survey", "geological", "geology"],
  feasibility_study: ["feasibility_study", "feasibility"],
  safety_assessment: ["safety_assessment", "safety"],
  energy_assessment: ["energy_assessment", "energy"],
};

const BLANK_TEMPLATE = {
  id: "tpl_blank",
  name: "空白模板",
  description: "从零开始创建报告大纲，适用于没有固定模板的特殊项目。",
  domain: "",
};

interface TemplateOption {
  id: string;
  name: string;
  description: string;
  domain: string;
}

async function fetchPublishedTemplates(): Promise<TemplateOption[]> {
  try {
    const data = await authFetch<{ templates: Array<{ id: string; name: string; domain: string; status: string }>; total: number }>(
      "/api/kf/templates?status=published&limit=100",
      {},
      "",
    );
    return (data.templates ?? []).map((t) => ({
      id: t.id,
      name: t.name,
      description: t.name,
      domain: t.domain,
    }));
  } catch {
    return [];
  }
}

const MEMBER_ROLES: MemberRole[] = ["owner", "member"];

// ─── CustomSelect ────────────────────────────────────────────────────────────────

function CustomSelect({
  value,
  onChange,
  options,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  options: SelectOption[];
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const selected = options.find((o) => o.value === value);

  return (
    <div className="relative w-full">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        className={cn(
          "flex h-[34px] w-full items-center justify-between rounded-md px-3 text-sm",
          "border bg-white transition-all duration-150",
          open ? "border-blue-500 ring-2 ring-blue-500/20" : "border-gray-200 hover:border-gray-300",
        )}
      >
        <span className={cn("truncate", selected ? "text-foreground" : "text-gray-400")}>
          {selected?.label ?? placeholder ?? "请选择"}
        </span>
        <ChevronDown
          className={cn("h-4 w-4 shrink-0 text-gray-400 transition-transform duration-200", open && "rotate-180")}
        />
      </button>
      {open && (
        <div className="absolute top-full left-0 z-50 mt-1 w-full overflow-hidden rounded-lg border border-gray-200 bg-white shadow-lg">
          {options.map((o) => (
            <button
              key={o.value}
              type="button"
              onClick={() => {
                onChange(o.value);
                setOpen(false);
              }}
              className={cn(
                "flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors",
                o.value === value
                  ? "bg-blue-50 font-medium text-blue-600"
                  : "text-foreground hover:bg-gray-50",
              )}
            >
              {o.label}
              {o.value === value && <Check className="ml-auto h-3.5 w-3.5 shrink-0 text-blue-600" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Sidebar ─────────────────────────────────────────────────────────────────────

function WizardSidebar({ currentStep }: { currentStep: WizardStep }) {
  return (
    <div className="flex h-full w-[220px] shrink-0 flex-col border-r border-gray-200 bg-white">
      {/* Logo */}
      <div className="flex h-[56px] items-center px-5">
        <span className="text-lg font-bold text-foreground">项目创建向导</span>
      </div>

      {/* Steps */}
      <div className="flex flex-col px-5 pt-6">
        {STEPS.map((s, i) => {
          const isActive = s.step === currentStep;
          const isCompleted = s.step < currentStep;
          return (
            <React.Fragment key={s.key}>
              <div className="flex items-center gap-3">
                <div
                  className={cn(
                    "flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold transition-colors",
                    isActive
                      ? "bg-blue-600 text-white"
                      : isCompleted
                        ? "bg-green-500 text-white"
                        : "bg-gray-200 text-gray-500",
                  )}
                >
                  {isCompleted ? <Check className="h-4 w-4" /> : s.step}
                </div>
                <span
                  className={cn(
                    "text-sm font-medium",
                    isActive ? "text-foreground" : isCompleted ? "text-green-600" : "text-gray-400",
                  )}
                >
                  步骤 {s.step}：{s.label}
                </span>
              </div>
              {i < STEPS.length - 1 && (
                <div
                  className={cn(
                    "ml-4 h-12 w-[1px]",
                    isCompleted ? "bg-green-500" : "bg-gray-200",
                  )}
                />
              )}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
}

// ─── Step 1: Basic Info ──────────────────────────────────────────────────────────

function StepBasicInfo({
  name,
  reportType,
  client,
  targetStandard,
  deadline,
  errors,
  onNameChange,
  onReportTypeChange,
  onClientChange,
  onTargetStandardChange,
  onDeadlineChange,
}: {
  name: string;
  reportType: ReportType;
  client: string;
  targetStandard: string;
  deadline: string;
  errors: { name?: string; client?: string };
  onNameChange: (v: string) => void;
  onReportTypeChange: (v: string) => void;
  onClientChange: (v: string) => void;
  onTargetStandardChange: (v: string) => void;
  onDeadlineChange: (v: string) => void;
}) {
  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-base font-semibold text-foreground">项目基本信息</h3>
        <p className="mt-1 text-[13px] text-[#475569]">
          填写项目的基本信息，带 <span className="text-red-500">*</span> 的为必填项
        </p>
      </div>

      <div className="space-y-5">
        <div className="space-y-1.5">
          <Label className="text-sm text-foreground">
            项目名称 <span className="text-red-500">*</span>
          </Label>
          <Input
            value={name}
            onChange={(e) => onNameChange(e.target.value)}
            placeholder="请输入项目名称"
            className={cn(
              "h-[34px] rounded-md bg-white text-sm",
              errors.name ? "border-red-500 focus-visible:ring-red-500/30" : "border-gray-200",
            )}
          />
          {errors.name && <p className="text-xs text-red-500">{errors.name}</p>}
        </div>

        <div className="space-y-1.5">
          <Label className="text-sm text-foreground">报告类型</Label>
          <CustomSelect
            value={reportType}
            onChange={onReportTypeChange}
            options={REPORT_TYPE_OPTIONS}
            placeholder="请选择报告类型"
          />
        </div>

        <div className="space-y-1.5">
          <Label className="text-sm text-foreground">
            客户单位 <span className="text-red-500">*</span>
          </Label>
          <Input
            value={client}
            onChange={(e) => onClientChange(e.target.value)}
            placeholder="请输入客户单位名称"
            className={cn(
              "h-[34px] rounded-md bg-white text-sm",
              errors.client ? "border-red-500 focus-visible:ring-red-500/30" : "border-gray-200",
            )}
          />
          {errors.client && <p className="text-xs text-red-500">{errors.client}</p>}
        </div>

        <div className="space-y-1.5">
          <Label className="text-sm text-foreground">目标标准</Label>
          <Input
            value={targetStandard}
            onChange={(e) => onTargetStandardChange(e.target.value)}
            placeholder="如 HJ 2.1-2016（选填）"
            className="h-[34px] rounded-md border-gray-200 bg-white text-sm"
          />
        </div>

        <div className="space-y-1.5">
          <Label className="text-sm text-foreground">截止日期</Label>
          <Popover>
            <PopoverTrigger asChild>
              <button
                type="button"
                className={cn(
                  "flex h-[34px] w-full items-center justify-between rounded-md border bg-white px-3 text-sm transition-colors",
                  deadline ? "border-gray-200 text-foreground" : "border-gray-200 text-gray-400",
                )}
              >
                <span>{deadline ? (() => { const [y, m, d] = deadline.split("-"); return `${y}年${Number(m)}月${Number(d)}日`; })() : "选择截止日期"}</span>
                <CalendarIcon className="h-4 w-4 shrink-0 text-gray-400" />
              </button>
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0" align="start">
              <Calendar
                mode="single"
                selected={deadline ? (() => { const [y, m, d] = deadline.split("-"); return new Date(Number(y), Number(m) - 1, Number(d)); })() : undefined}
                onSelect={(date) => onDeadlineChange(date ? `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}` : "")}
                initialFocus
              />
            </PopoverContent>
          </Popover>
        </div>
      </div>
    </div>
  );
}

// ─── Step 2: Template Selection ──────────────────────────────────────────────────

function StepTemplate({
  templateId,
  templates,
  onTemplateChange,
  onSkip,
}: {
  templateId: string;
  templates: TemplateOption[];
  onTemplateChange: (id: string) => void;
  onSkip: () => void;
}) {
  const options = [...templates, BLANK_TEMPLATE];

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-base font-semibold text-foreground">选择报告模板</h3>
        <p className="mt-1 text-[13px] text-[#475569]">
          选择一个来自知识工厂的报告模板作为项目基础结构，或跳过此步骤
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {options.map((tpl) => (
          <button
            key={tpl.id}
            type="button"
            onClick={() => onTemplateChange(tpl.id)}
            className={cn(
              "flex flex-col items-start rounded-lg border-2 p-4 text-left transition-all",
              templateId === tpl.id
                ? "border-blue-500 bg-blue-50/50"
                : "border-gray-200 bg-white hover:border-gray-300 hover:shadow-sm",
            )}
          >
            <div className="flex w-full items-start gap-3">
              <div
                className={cn(
                  "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg",
                  templateId === tpl.id ? "bg-blue-100 text-blue-600" : "bg-gray-100 text-gray-500",
                )}
              >
                <FileText className="h-5 w-5" />
              </div>
              <div className="min-w-0 flex-1">
                <p
                  className={cn(
                    "text-sm font-medium",
                    templateId === tpl.id ? "text-blue-600" : "text-foreground",
                  )}
                >
                  {tpl.name}
                </p>
                <p className="mt-1 line-clamp-2 text-xs text-gray-500">{tpl.description}</p>
              </div>
            </div>
            {templateId === tpl.id && (
              <div className="mt-2 flex w-full items-center gap-1 text-xs text-blue-600">
                <CheckCircle2 className="h-3.5 w-3.5" />
                已选择
              </div>
            )}
          </button>
        ))}
      </div>

      <div className="flex justify-end">
        <button
          type="button"
          onClick={onSkip}
          className="text-sm text-gray-400 transition-colors hover:text-blue-500"
        >
          跳过此步骤
        </button>
      </div>
    </div>
  );
}

// ─── Step 3: Team Building ───────────────────────────────────────────────────────

function StepTeam({
  leader,
  members,
  onSetLeader,
  onAddMember,
  onRemoveMember,
  onSkip,
}: {
  leader: string;
  members: string[];
  onSetLeader: (userId: string) => void;
  onAddMember: (userId: string) => void;
  onRemoveMember: (userId: string) => void;
  onSkip: () => void;
}) {
  const [searchValue, setSearchValue] = useState("");

  const handleAddMember = () => {
    const trimmed = searchValue.trim();
    if (!trimmed) return;
    if (leader === trimmed || members.includes(trimmed)) {
      toast.error("该成员已在团队中");
      return;
    }
    onAddMember(trimmed);
    setSearchValue("");
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-base font-semibold text-foreground">组建项目团队</h3>
        <p className="mt-1 text-[13px] text-[#475569]">
          团队由组长和组员组成，负责报告编写。审核、批准等环节由团队外的相关部门或领导负责。
        </p>
      </div>

      {/* Search + Add */}
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <Input
            value={searchValue}
            onChange={(e) => setSearchValue(e.target.value)}
            placeholder="搜索或输入成员名称"
            className="h-[34px] rounded-md border-gray-200 bg-white pl-9 text-sm"
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                handleAddMember();
              }
            }}
          />
        </div>
        <Button type="button" variant="outline" onClick={handleAddMember} className="h-[34px] shrink-0 gap-1">
          <Plus className="h-3.5 w-3.5" />
          添加组员
        </Button>
      </div>

      {/* Leader */}
      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-foreground">组长</span>
            <span className="rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-medium text-blue-600">必选</span>
          </div>
          <span className="text-[11px] text-gray-400">负责创建任务、选择模板、提交审核</span>
        </div>
        {!leader ? (
          <div className="flex items-center gap-2 rounded-lg border border-dashed border-gray-200 px-3 py-3 text-xs text-gray-400">
            <UserCircle className="h-4 w-4" />
            请点击成员设为组长，或在上方搜索后点击"设为组长"
          </div>
        ) : (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-blue-50 px-3 py-1 text-sm font-medium text-blue-600">
            <UserCircle className="h-3.5 w-3.5" />
            {leader}
            <button
              type="button"
              onClick={() => onSetLeader("")}
              className="ml-0.5 rounded-full p-0.5 transition-colors hover:bg-blue-100"
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        )}
      </div>

      {/* Members */}
      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <div className="mb-3 flex items-center justify-between">
          <span className="text-sm font-medium text-foreground">组员</span>
          <span className="text-[11px] text-gray-400">负责修改AI生成的初稿 · {members.length} 人</span>
        </div>
        {members.length === 0 ? (
          <div className="flex items-center gap-2 rounded-lg border border-dashed border-gray-200 px-3 py-3 text-xs text-gray-400">
            <UserCircle className="h-4 w-4" />
            暂未添加组员
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {members.map((userId) => (
              <span
                key={userId}
                className="inline-flex items-center gap-1.5 rounded-full bg-gray-50 px-3 py-1 text-sm font-medium text-foreground"
              >
                <UserCircle className="h-3.5 w-3.5 text-gray-400" />
                {userId}
                <button
                  type="button"
                  onClick={() => onRemoveMember(userId)}
                  className="ml-0.5 rounded-full p-0.5 transition-colors hover:bg-gray-200"
                >
                  <X className="h-3 w-3" />
                </button>
                <button
                  type="button"
                  onClick={() => { onSetLeader(userId); onRemoveMember(userId); }}
                  className="ml-0.5 rounded px-1.5 py-0.5 text-[10px] text-blue-600 transition-colors hover:bg-blue-50"
                >
                  设为组长
                </button>
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="flex justify-end">
        <button
          type="button"
          onClick={onSkip}
          className="text-sm text-gray-400 transition-colors hover:text-blue-500"
        >
          跳过此步骤
        </button>
      </div>
    </div>
  );
}

// ─── Step 4: Confirm ─────────────────────────────────────────────────────────────

function StepConfirm({
  name,
  reportType,
  client,
  targetStandard,
  templateId,
  templates,
  leader,
  teamMembers,
}: {
  name: string;
  reportType: ReportType;
  client: string;
  targetStandard: string;
  templateId: string;
  templates: TemplateOption[];
  leader: string;
  teamMembers: string[];
}) {
  const allTemplates = [...templates, BLANK_TEMPLATE];
  const selectedTemplate = allTemplates.find((t) => t.id === templateId);
  const totalMembers = (leader ? 1 : 0) + teamMembers.length;

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-base font-semibold text-foreground">确认项目信息</h3>
        <p className="mt-1 text-[13px] text-[#475569]">请核实以下信息无误后点击创建</p>
      </div>

      <div className="space-y-4">
        {/* Basic info card */}
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <div className="mb-3 flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-blue-50">
              <FileText className="h-4 w-4 text-blue-600" />
            </div>
            <span className="text-sm font-medium text-foreground">基本信息</span>
          </div>
          <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
            <div>
              <span className="text-gray-400">项目名称</span>
              <p className="mt-0.5 text-foreground">{name}</p>
            </div>
            <div>
              <span className="text-gray-400">报告类型</span>
              <p className="mt-0.5 text-foreground">{REPORT_TYPE_LABELS[reportType]}</p>
            </div>
            <div>
              <span className="text-gray-400">客户单位</span>
              <p className="mt-0.5 text-foreground">{client}</p>
            </div>
            {targetStandard && (
              <div>
                <span className="text-gray-400">目标标准</span>
                <p className="mt-0.5 text-foreground">{targetStandard}</p>
              </div>
            )}
          </div>
        </div>

        {/* Template card */}
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <div className="mb-3 flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-purple-50">
              <FileText className="h-4 w-4 text-purple-600" />
            </div>
            <span className="text-sm font-medium text-foreground">报告模板</span>
          </div>
          <div className="text-sm">
            <span className="text-gray-400">选用模板</span>
            <p className="mt-0.5 text-foreground">{selectedTemplate?.name ?? "未选择模板"}</p>
          </div>
        </div>

        {/* Team card */}
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <div className="mb-3 flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-green-50">
              <UserCircle className="h-4 w-4 text-green-600" />
            </div>
            <span className="text-sm font-medium text-foreground">项目团队</span>
            <span className="text-xs text-gray-400">{totalMembers} 人</span>
          </div>
          {totalMembers === 0 ? (
            <p className="text-sm text-gray-400">暂未分配团队成员</p>
          ) : (
            <div className="space-y-2">
              {leader && (
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-gray-400">组长</span>
                  <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-600">
                    {leader}
                  </span>
                </div>
              )}
              {teamMembers.length > 0 && (
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-gray-400">组员</span>
                  <div className="flex gap-1">
                    {teamMembers.map((userId) => (
                      <span
                        key={userId}
                        className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-foreground"
                      >
                        {userId}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Main Component ──────────────────────────────────────────────────────────────

export function ProjectCreateWizard() {
  const router = useRouter();

  // Step
  const [step, setStep] = useState<WizardStep>(1);

  // Step 1: Basic info
  const [name, setName] = useState("");
  const [reportType, setReportType] = useState<ReportType>("environmental_impact");
  const [client, setClient] = useState("");
  const [targetStandard, setTargetStandard] = useState("");
  const [deadline, setDeadline] = useState("");

  // Step 2: Template
  const [templateId, setTemplateId] = useState<string>("tpl_blank");
  const [templates, setTemplates] = useState<TemplateOption[]>([]);

  // Fetch published templates on mount
  React.useEffect(() => {
    fetchPublishedTemplates().then((fetched) => {
      setTemplates(fetched);
      // Auto-select a template matching the current report type
      const domains = REPORT_TYPE_TO_DOMAIN[reportType] ?? [];
      const match = fetched.find((t) => domains.includes(t.domain));
      if (match) setTemplateId(match.id);
    });
  }, []);

  // Step 3: Team
  const [leader, setLeader] = useState("");
  const [teamMembers, setTeamMembers] = useState<string[]>([]);

  // Submitting
  const [submitting, setSubmitting] = useState(false);

  // Validation errors
  const [errors, setErrors] = useState<{ name?: string; client?: string }>({});

  // Navigation
  const goNext = useCallback(() => {
    if (step === 1) {
      const newErrors: { name?: string; client?: string } = {};
      if (!name.trim()) {
        newErrors.name = "请输入项目名称";
      }
      if (!client.trim()) {
        newErrors.client = "请输入客户单位";
      }
      if (Object.keys(newErrors).length > 0) {
        setErrors(newErrors);
        return;
      }
      setErrors({});
    }
    if (step < 4) {
      setStep((s) => (s + 1) as WizardStep);
    }
  }, [step, name, client]);

  const goPrev = useCallback(() => {
    if (step > 1) {
      setStep((s) => (s - 1) as WizardStep);
    } else {
      router.push("/projects");
    }
  }, [step, router]);

  // Skip helpers
  const skipToNext = useCallback(() => {
    if (step < 4) {
      setStep((s) => (s + 1) as WizardStep);
    }
  }, [step]);

  // Team operations
  const addTeamMember = useCallback((userId: string) => {
    setTeamMembers((prev) => [...prev, userId]);
  }, []);

  const removeTeamMember = useCallback((userId: string) => {
    setTeamMembers((prev) => prev.filter((id) => id !== userId));
  }, []);

  // Resolve template_id for submission: match by domain if using a real template
  const resolveTemplateId = useCallback((): string | undefined => {
    if (templateId === "tpl_blank") return undefined;
    return templateId || undefined;
  }, [templateId]);

  // Submit
  const handleCreate = async () => {
    setSubmitting(true);
    try {
      const memberList: { userId: string; role: MemberRole }[] = [];
      if (leader) {
        memberList.push({ userId: leader, role: "owner" });
      }
      for (const userId of teamMembers) {
        memberList.push({ userId, role: "member" });
      }

      const project = await projectApi.create({
        name: name.trim(),
        reportType,
        templateId: resolveTemplateId(),
        members: memberList.length > 0 ? memberList : undefined,
      });

      toast.success("项目创建成功");
      router.push(`/projects/${project.id}`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "项目创建失败";
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const handleBack = () => {
    router.push("/projects");
  };

  return (
    <div className="flex h-screen bg-[#F9FAFB]">
      {/* Sidebar */}
      <WizardSidebar currentStep={step} />

      {/* Main content */}
      <div className="flex flex-1 flex-col items-center overflow-y-auto">
        <div className="my-8 w-full max-w-[640px] rounded-[8px] border border-gray-200 bg-white">
          {/* Header */}
          <div className="flex h-[56px] items-center gap-3 border-b border-gray-200 px-6">
            <button
              type="button"
              onClick={goPrev}
              className="flex h-8 w-8 items-center justify-center rounded-md text-gray-400 transition-colors hover:bg-gray-100 hover:text-foreground"
            >
              <ArrowLeft className="h-5 w-5" />
            </button>
            <h2 className="text-base font-semibold text-foreground">新建项目</h2>
            <span className="text-sm text-gray-400">步骤 {step}/4</span>
          </div>

          {/* Content */}
          <div className="min-h-[400px] px-6 py-6">
            {step === 1 && (
              <StepBasicInfo
                name={name}
                reportType={reportType}
                client={client}
                targetStandard={targetStandard}
                deadline={deadline}
                errors={errors}
                onNameChange={(v) => { setName(v); if (errors.name) setErrors((e) => ({ ...e, name: undefined })); }}
                onReportTypeChange={(v) => setReportType(v as ReportType)}
                onClientChange={(v) => { setClient(v); if (errors.client) setErrors((e) => ({ ...e, client: undefined })); }}
                onTargetStandardChange={setTargetStandard}
                onDeadlineChange={setDeadline}
              />
            )}
            {step === 2 && (
              <StepTemplate
                templateId={templateId}
                templates={templates}
                onTemplateChange={setTemplateId}
                onSkip={skipToNext}
              />
            )}
            {step === 3 && (
              <StepTeam
                leader={leader}
                members={teamMembers}
                onSetLeader={setLeader}
                onAddMember={addTeamMember}
                onRemoveMember={removeTeamMember}
                onSkip={skipToNext}
              />
            )}
            {step === 4 && (
              <StepConfirm
                name={name}
                reportType={reportType}
                client={client}
                targetStandard={targetStandard}
                templateId={templateId}
                templates={templates}
                leader={leader}
                teamMembers={teamMembers}
              />
            )}
          </div>

          {/* Footer */}
          <div className="flex h-[60px] items-center justify-between border-t border-gray-200 px-6">
            <div>
              {step === 1 && (
                <Button type="button" variant="ghost" onClick={handleBack} className="text-gray-500">
                  取消
                </Button>
              )}
            </div>
            <div className="flex gap-3">
              {step > 1 && (
                <Button type="button" variant="outline" onClick={goPrev} className="gap-1">
                  上一步
                </Button>
              )}
              {step < 4 ? (
                <Button type="button" onClick={goNext} className="gap-1 bg-blue-600 hover:bg-blue-700">
                  下一步
                  <ChevronRight className="h-4 w-4" />
                </Button>
              ) : (
                <Button
                  type="button"
                  onClick={handleCreate}
                  disabled={submitting}
                  className="gap-1.5 bg-green-600 hover:bg-green-700"
                >
                  {submitting ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      创建中...
                    </>
                  ) : (
                    <>
                      <Sparkles className="h-4 w-4" />
                      创建项目
                    </>
                  )}
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
