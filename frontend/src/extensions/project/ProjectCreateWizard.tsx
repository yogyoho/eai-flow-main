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
  Search,
  Sparkles,
  UserCircle,
  X,
} from "lucide-react";
import { useRouter } from "next/navigation";
import React, { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { projectApi } from "@/extensions/project/api";
import { workflowApi } from "@/extensions/workflow/api";
import {
  MEMBER_ROLE_LABELS,
  type MemberRole,
} from "@/extensions/project/types";
import { authFetch } from "@/extensions/api/client";
import { useReportTypes, getReportTypeLabel } from "@/extensions/project/hooks/useReportTypes";
import { cn } from "@/lib/utils";

// ─── Types ──────────────────────────────────────────────────────────────────────

interface SelectOption {
  value: string;
  label: string;
}

type WizardStep = 1 | 2 | 3 | 4 | 5;

// ─── Constants ───────────────────────────────────────────────────────────────────

const STEPS: { step: WizardStep; key: string; label: string }[] = [
  { step: 1, key: "1", label: "基本信息" },
  { step: 2, key: "2", label: "内容大纲" },
  { step: 3, key: "3", label: "工作流" },
  { step: 4, key: "4", label: "组建团队" },
  { step: 5, key: "5", label: "确认创建" },
];

interface TemplateOption {
  id: string;
  name: string;
  description: string;
  domain: string;
  /** Non-empty when this is a workflow template (WorkflowDefinition id). */
  workflowDefId?: string;
}

const BLANK_TEMPLATE: TemplateOption = {
  id: "tpl_blank",
  name: "空白模板",
  description: "从零开始创建报告大纲，适用于没有固定模板的特殊项目。",
  domain: "",
};

const SKIP_WORKFLOW: TemplateOption = {
  id: "wf_skip",
  name: "跳过工作流",
  description: "不使用自动化工作流，手动管理项目进度和章节写作。",
  domain: "",
};

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

async function fetchWorkflowTemplates(reportType?: string): Promise<TemplateOption[]> {
  try {
    const res = await workflowApi.listTemplates(reportType);
    return res.items.map((t) => ({
      id: `wf_${t.id}`,
      name: t.name,
      description: t.name,
      domain: t.reportType ?? "",
      workflowDefId: t.id,
    }));
  } catch {
    return [];
  }
}

const MEMBER_ROLES: MemberRole[] = ["owner", "member"];

/** A team member carries a display name plus the UUID we submit to the API.
 *  DF-2: the wizard used to submit usernames and 422 on UUID validation. */
interface TeamMember {
  id: string;
  username: string;
  fullName?: string;
}

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
  reportTypeOptions,
  onNameChange,
  onReportTypeChange,
  onClientChange,
  onTargetStandardChange,
  onDeadlineChange,
}: {
  name: string;
  reportType: string;
  client: string;
  targetStandard: string;
  deadline: string;
  errors: { name?: string; client?: string };
  reportTypeOptions: SelectOption[];
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
            options={reportTypeOptions}
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
  // Only KF templates (no workflow templates) + blank
  const options = [...templates.filter((t) => !t.workflowDefId), BLANK_TEMPLATE];

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-base font-semibold text-foreground">选择内容大纲模板</h3>
        <p className="mt-1 text-[13px] text-[#475569]">
          选择一个内容模板定义报告的章节大纲结构，或使用空白模板从零开始
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

// ─── Step 3: Workflow Template ──────────────────────────────────────────────────

function StepWorkflow({
  workflowId,
  workflowTemplates,
  onWorkflowChange,
  onSkip,
}: {
  workflowId: string;
  workflowTemplates: TemplateOption[];
  onWorkflowChange: (id: string) => void;
  onSkip: () => void;
}) {
  const options = [...workflowTemplates, SKIP_WORKFLOW];

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-base font-semibold text-foreground">选择工作流模板</h3>
        <p className="mt-1 text-[13px] text-[#475569]">
          工作流定义项目的写作流程：分阶段写作、AI 生成初稿、人工审阅等。选择一个适合项目类型的流程模板，或跳过手动管理
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {options.map((tpl) => (
          <button
            key={tpl.id}
            type="button"
            onClick={() => onWorkflowChange(tpl.id)}
            className={cn(
              "flex flex-col items-start rounded-lg border-2 p-4 text-left transition-all",
              workflowId === tpl.id
                ? "border-violet-500 bg-violet-50/50"
                : "border-gray-200 bg-white hover:border-gray-300 hover:shadow-sm",
            )}
          >
            <div className="flex w-full items-start gap-3">
              <div
                className={cn(
                  "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg",
                  workflowId === tpl.id ? "bg-violet-100 text-violet-600" : "bg-gray-100 text-gray-500",
                )}
              >
                <Sparkles className="h-5 w-5" />
              </div>
              <div className="min-w-0 flex-1">
                <p
                  className={cn(
                    "text-sm font-medium",
                    workflowId === tpl.id ? "text-violet-600" : "text-foreground",
                  )}
                >
                  {tpl.name}
                </p>
                <p className="mt-1 line-clamp-2 text-xs text-gray-500">{tpl.description}</p>
              </div>
            </div>
            {workflowId === tpl.id && (
              <div className="mt-2 flex w-full items-center gap-1 text-xs text-violet-600">
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
  leader: TeamMember | null;
  members: TeamMember[];
  onSetLeader: (m: TeamMember | null) => void;
  onAddMember: (m: TeamMember) => void;
  onRemoveMember: (id: string) => void;
  onSkip: () => void;
}) {
  const [searchValue, setSearchValue] = useState("");
  const [results, setResults] = useState<TeamMember[]>([]);
  const [searching, setSearching] = useState(false);

  // Debounced user search — resolve a display name to a UUID before adding
  // (DF-2: the wizard previously submitted raw usernames and 422'd).
  useEffect(() => {
    const q = searchValue.trim();
    if (!q) {
      setResults([]);
      return;
    }
    const timer = setTimeout(async () => {
      setSearching(true);
      try {
        const resp = await fetch(`/api/extensions/users/search?keyword=${encodeURIComponent(q)}`);
        if (resp.ok) {
          const data = await resp.json();
          setResults((data.users ?? data.items ?? []).slice(0, 10));
        }
      } catch {
        /* ignore */
      } finally {
        setSearching(false);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [searchValue]);

  const existingIds = new Set([
    ...members.map((m) => m.id),
    ...(leader ? [leader.id] : []),
  ]);

  const pick = (u: TeamMember) => {
    if (existingIds.has(u.id)) {
      toast.error("该成员已在团队中");
      return;
    }
    onAddMember(u);
    setSearchValue("");
    setResults([]);
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
      <div className="relative flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <Input
            value={searchValue}
            onChange={(e) => setSearchValue(e.target.value)}
            placeholder="搜索用户名/姓名添加组员"
            className="h-[34px] rounded-md border-gray-200 bg-white pl-9 text-sm"
          />
          {searchValue.trim() && (
            <div className="absolute top-full left-0 z-50 mt-1 max-h-60 w-full overflow-auto rounded-lg border border-gray-200 bg-white shadow-lg">
              {searching && <div className="px-3 py-2 text-xs text-gray-400">搜索中…</div>}
              {!searching && results.length === 0 && (
                <div className="px-3 py-2 text-xs text-gray-400">无匹配用户</div>
              )}
              {results.map((u) => (
                <button
                  key={u.id}
                  type="button"
                  onClick={() => pick(u)}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors hover:bg-gray-50"
                >
                  <div className="flex h-6 w-6 items-center justify-center rounded-full bg-muted text-[10px] font-medium">
                    {u.username.charAt(0).toUpperCase()}
                  </div>
                  <span>{u.username}</span>
                  {u.fullName && <span className="text-muted-foreground">({u.fullName})</span>}
                </button>
              ))}
            </div>
          )}
        </div>
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
            请先添加组员，再在组员卡片上点击"设为组长"
          </div>
        ) : (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-blue-50 px-3 py-1 text-sm font-medium text-blue-600">
            <UserCircle className="h-3.5 w-3.5" />
            {leader.username}
            <button
              type="button"
              onClick={() => onSetLeader(null)}
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
            {members.map((m) => (
              <span
                key={m.id}
                className="inline-flex items-center gap-1.5 rounded-full bg-gray-50 px-3 py-1 text-sm font-medium text-foreground"
              >
                <UserCircle className="h-3.5 w-3.5 text-gray-400" />
                {m.username}
                <button
                  type="button"
                  onClick={() => onRemoveMember(m.id)}
                  className="ml-0.5 rounded-full p-0.5 transition-colors hover:bg-gray-200"
                >
                  <X className="h-3 w-3" />
                </button>
                <button
                  type="button"
                  onClick={() => { onSetLeader(m); onRemoveMember(m.id); }}
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
  reportTypeOptions,
  autoStartWorkflow,
  onAutoStartChange,
  workflowId,
  workflowTemplates,
}: {
  name: string;
  reportType: string;
  client: string;
  targetStandard: string;
  templateId: string;
  templates: TemplateOption[];
  leader: TeamMember | null;
  teamMembers: TeamMember[];
  reportTypeOptions: SelectOption[];
  autoStartWorkflow: boolean;
  onAutoStartChange: (v: boolean) => void;
  workflowId: string;
  workflowTemplates: TemplateOption[];
}) {
  const allTemplates = [...templates, BLANK_TEMPLATE];
  const selectedTemplate = allTemplates.find((t) => t.id === templateId);
  const allWorkflows = [...workflowTemplates, SKIP_WORKFLOW];
  const selectedWorkflow = allWorkflows.find((t) => t.id === workflowId);
  const totalMembers = (leader ? 1 : 0) + teamMembers.length;
  const hasWorkflow = workflowId !== "wf_skip";

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
              <p className="mt-0.5 text-foreground">{getReportTypeLabel(reportType)}</p>
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

        {/* Content template card */}
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <div className="mb-3 flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-purple-50">
              <FileText className="h-4 w-4 text-purple-600" />
            </div>
            <span className="text-sm font-medium text-foreground">内容大纲模板</span>
          </div>
          <div className="text-sm">
            <span className="text-gray-400">选用模板</span>
            <p className="mt-0.5 text-foreground">{selectedTemplate?.name ?? "未选择模板"}</p>
          </div>
        </div>

        {/* Workflow template card */}
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <div className="mb-3 flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-violet-50">
              <Sparkles className="h-4 w-4 text-violet-600" />
            </div>
            <span className="text-sm font-medium text-foreground">工作流模板</span>
          </div>
          <div className="text-sm">
            <span className="text-gray-400">选用工作流</span>
            <p className="mt-0.5 text-foreground">{selectedWorkflow?.name ?? "未选择工作流"}</p>
          </div>
          {hasWorkflow && (
            <label className="mt-3 flex items-center gap-2 rounded-md bg-amber-50 px-3 py-2 text-sm cursor-pointer select-none border border-amber-200">
              <input
                type="checkbox"
                checked={autoStartWorkflow}
                onChange={(e) => onAutoStartChange(e.target.checked)}
                className="h-4 w-4 rounded border-amber-300 text-amber-600 focus:ring-amber-500"
              />
              <div>
                <span className="font-medium text-amber-800">创建后自动启动工作流</span>
                <p className="text-xs text-amber-600">勾选后项目创建完成将立即启动工作流引擎，无需手动操作</p>
              </div>
            </label>
          )}
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
                    {leader.username}
                  </span>
                </div>
              )}
              {teamMembers.length > 0 && (
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-gray-400">组员</span>
                  <div className="flex gap-1">
                    {teamMembers.map((m) => (
                      <span
                        key={m.id}
                        className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-foreground"
                      >
                        {m.username}
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
  const [reportType, setReportType] = useState<string>("");
  const [client, setClient] = useState("");
  const [targetStandard, setTargetStandard] = useState("");
  const [deadline, setDeadline] = useState("");

  // Dynamic report type options from report_type business dictionary
  const { options: reportTypeOptions } = useReportTypes();

  // Step 2: Content template (KF templates only)
  const [templateId, setTemplateId] = useState<string>("tpl_blank");
  const [kfTemplates, setKfTemplates] = useState<TemplateOption[]>([]);

  // Step 3: Workflow template (workflow definitions only)
  const [workflowId, setWorkflowId] = useState<string>("wf_skip");
  const [workflowTemplates, setWorkflowTemplates] = useState<TemplateOption[]>([]);

  // Fetch templates on mount
  React.useEffect(() => {
    Promise.all([fetchPublishedTemplates(), fetchWorkflowTemplates(reportType)]).then(
      ([kfs, wfs]) => {
        setKfTemplates(kfs);
        setWorkflowTemplates(wfs);
      },
    );
  }, [reportType]);

  // Step 4: Team
  const [leader, setLeader] = useState<TeamMember | null>(null);
  const [teamMembers, setTeamMembers] = useState<TeamMember[]>([]);

  // Auto-start workflow option
  const [autoStartWorkflow, setAutoStartWorkflow] = useState(true);

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
    if (step < 5) {
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
    if (step < 5) {
      setStep((s) => (s + 1) as WizardStep);
    }
  }, [step]);

  // Team operations
  const addTeamMember = useCallback((m: TeamMember) => {
    setTeamMembers((prev) => [...prev, m]);
  }, []);

  const removeTeamMember = useCallback((id: string) => {
    setTeamMembers((prev) => prev.filter((m) => m.id !== id));
  }, []);

  // Resolve template_id for submission
  const resolveTemplateId = useCallback((): string | undefined => {
    if (templateId === "tpl_blank") return undefined;
    return templateId || undefined;
  }, [templateId]);

  // Resolve workflow_id for submission
  const resolveWorkflowId = useCallback((): string | undefined => {
    if (workflowId === "wf_skip") return undefined;
    // Workflow IDs are stored as "wf_<uuid>" — strip the prefix
    if (workflowId.startsWith("wf_")) {
      return workflowId.slice(3);
    }
    return workflowId || undefined;
  }, [workflowId]);

  // Submit
  const handleCreate = async () => {
    setSubmitting(true);
    try {
      const memberList: { userId: string; role: MemberRole }[] = [];
      if (leader) {
        memberList.push({ userId: leader.id, role: "owner" });
      }
      for (const m of teamMembers) {
        memberList.push({ userId: m.id, role: "member" });
      }

      const workflowId = resolveWorkflowId();
      const project = await projectApi.create({
        name: name.trim(),
        reportType: reportType as import("@/extensions/project/types").ReportType,
        templateId: resolveTemplateId(),
        workflowId,
        autoStartWorkflow: autoStartWorkflow && !!workflowId,
        members: memberList.length > 0 ? memberList : undefined,
      });

      if (workflowId && autoStartWorkflow) {
        toast.success("项目创建成功，工作流已启动");
      } else {
        toast.success("项目创建成功");
      }

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
            <span className="text-sm text-gray-400">步骤 {step}/5</span>
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
                reportTypeOptions={reportTypeOptions}
                onNameChange={(v) => { setName(v); if (errors.name) setErrors((e) => ({ ...e, name: undefined })); }}
                onReportTypeChange={(v) => setReportType(v )}
                onClientChange={(v) => { setClient(v); if (errors.client) setErrors((e) => ({ ...e, client: undefined })); }}
                onTargetStandardChange={setTargetStandard}
                onDeadlineChange={setDeadline}
              />
            )}
            {step === 2 && (
              <StepTemplate
                templateId={templateId}
                templates={kfTemplates}
                onTemplateChange={setTemplateId}
                onSkip={skipToNext}
              />
            )}
            {step === 3 && (
              <StepWorkflow
                workflowId={workflowId}
                workflowTemplates={workflowTemplates}
                onWorkflowChange={setWorkflowId}
                onSkip={skipToNext}
              />
            )}
            {step === 4 && (
              <StepTeam
                leader={leader}
                members={teamMembers}
                onSetLeader={setLeader}
                onAddMember={addTeamMember}
                onRemoveMember={removeTeamMember}
                onSkip={skipToNext}
              />
            )}
            {step === 5 && (
              <StepConfirm
                name={name}
                reportType={reportType}
                client={client}
                targetStandard={targetStandard}
                templateId={templateId}
                templates={kfTemplates}
                leader={leader}
                teamMembers={teamMembers}
                reportTypeOptions={reportTypeOptions}
                autoStartWorkflow={autoStartWorkflow}
                onAutoStartChange={setAutoStartWorkflow}
                workflowId={workflowId}
                workflowTemplates={workflowTemplates}
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
              {step < 5 ? (
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
