"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  ChevronLeft,
  ChevronRight,
  Plus,
  UserCircle,
  FileText,
  Loader2,
  CheckCircle2,
  ChevronDown,
  Trash2,
} from "lucide-react";
import React, { useState, useEffect, useRef, useCallback } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { projectApi } from "./api";
import {
  REPORT_TYPE_LABELS,
  MEMBER_ROLE_LABELS,
  type ReportProject,
  type ReportType,
  type MemberRole,
} from "./types";

// ─── Types ──────────────────────────────────────────────────────────────────────

interface ProjectCreateWizardProps {
  open: boolean;
  onClose: () => void;
  onCreated: (project: ReportProject) => void;
}

interface SelectOption {
  value: string;
  label: string;
}

interface OutlineItem {
  id: string;
  title: string;
  children: OutlineItem[];
}

interface MockUser {
  id: string;
  name: string;
}

type WizardStep = 1 | 2 | 3 | 4;

// ─── Constants ───────────────────────────────────────────────────────────────────

const STEPS: { step: WizardStep; label: string }[] = [
  { step: 1, label: "基本信息" },
  { step: 2, label: "选择模板" },
  { step: 3, label: "报告大纲" },
  { step: 4, label: "成员分配" },
];

const REPORT_TYPE_OPTIONS: SelectOption[] = Object.entries(REPORT_TYPE_LABELS).map(
  ([value, label]) => ({ value, label }),
);

const MOCK_TEMPLATES = [
  {
    id: "tpl_env",
    name: "环境影响评价报告模板",
    description: "适用于建设项目的环境影响评价报告，包含环境现状调查、影响预测与评价、环境保护措施等章节。",
  },
  {
    id: "tpl_geo",
    name: "地质勘查报告模板",
    description: "适用于地质勘查项目的报告模板，包含地质概况、勘查方法、勘查成果等章节。",
  },
  {
    id: "tpl_feasibility",
    name: "可行性研究报告模板",
    description: "适用于各类建设项目的可行性研究报告，包含项目概述、市场分析、技术方案、经济评价等章节。",
  },
  {
    id: "tpl_blank",
    name: "空白模板",
    description: "从零开始创建报告大纲，适用于没有固定模板的特殊项目。",
  },
];

const MOCK_USERS: MockUser[] = [
  { id: "u1", name: "张三" },
  { id: "u2", name: "李四" },
  { id: "u3", name: "王五" },
];

const MEMBER_ROLES: MemberRole[] = ["manager", "writer", "reviewer", "issuer"];

const DEFAULT_OUTLINES: Record<string, OutlineItem[]> = {
  environmental_impact: [
    { id: "o1", title: "第一章 概述", children: [] },
    { id: "o2", title: "第二章 环境现状调查与评价", children: [] },
    { id: "o3", title: "第三章 环境影响预测与评价", children: [] },
    { id: "o4", title: "第四章 环境保护措施及其技术经济论证", children: [] },
    { id: "o5", title: "第五章 环境影响经济损益分析", children: [] },
    { id: "o6", title: "第六章 环境管理与监测计划", children: [] },
  ],
  geological_survey: [
    { id: "o1", title: "第一章 概述", children: [] },
    { id: "o2", title: "第二章 地质概况", children: [] },
    { id: "o3", title: "第三章 勘查方法及工作量", children: [] },
    { id: "o4", title: "第四章 勘查成果", children: [] },
    { id: "o5", title: "第五章 结论与建议", children: [] },
  ],
  feasibility_study: [
    { id: "o1", title: "第一章 总论", children: [] },
    { id: "o2", title: "第二章 市场分析与预测", children: [] },
    { id: "o3", title: "第三章 建设规模与产品方案", children: [] },
    { id: "o4", title: "第四章 技术方案", children: [] },
    { id: "o5", title: "第五章 投资估算与资金筹措", children: [] },
    { id: "o6", title: "第六章 财务评价", children: [] },
    { id: "o7", title: "第七章 结论与建议", children: [] },
  ],
  safety_assessment: [
    { id: "o1", title: "第一章 概述", children: [] },
    { id: "o2", title: "第二章 危险有害因素辨识与分析", children: [] },
    { id: "o3", title: "第三章 评价单元划分与评价方法选择", children: [] },
    { id: "o4", title: "第四章 定性定量评价", children: [] },
    { id: "o5", title: "第五章 安全对策措施与建议", children: [] },
  ],
  energy_assessment: [
    { id: "o1", title: "第一章 概述", children: [] },
    { id: "o2", title: "第二章 项目概况", children: [] },
    { id: "o3", title: "第三章 能源供应状况分析", children: [] },
    { id: "o4", title: "第四章 项目建设方案的节能分析", children: [] },
    { id: "o5", title: "第五章 节能措施评估", children: [] },
  ],
  other: [
    { id: "o1", title: "第一章 概述", children: [] },
  ],
};

const BLANK_OUTLINE: OutlineItem[] = [
  { id: "o1", title: "第一章 概述", children: [] },
];

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
  const ref = useRef<HTMLDivElement>(null);
  const selected = options.find((o) => o.value === value);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div ref={ref} className="relative w-full">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className={cn(
          "flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2.5 text-sm",
          "border bg-background transition-all duration-150",
          open
            ? "border-primary shadow-sm ring-2 ring-ring/50"
            : "border-input hover:border-input hover:shadow-sm",
        )}
      >
        <span
          className={cn(
            "flex min-w-0 items-center gap-2",
            selected ? "text-foreground" : "text-muted-foreground",
          )}
        >
          <span className="truncate">{selected?.label ?? placeholder ?? "请选择"}</span>
        </span>
        <ChevronDown
          className={cn(
            "h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200",
            open && "rotate-180",
          )}
        />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.98 }}
            transition={{ duration: 0.15 }}
            className="absolute top-full right-0 left-0 z-50 mt-1.5 overflow-hidden rounded-xl border border-border bg-background shadow-lg shadow-black/5"
          >
            {options.map((o) => (
              <button
                key={o.value}
                type="button"
                onClick={() => {
                  onChange(o.value);
                  setOpen(false);
                }}
                className={cn(
                  "flex w-full items-center gap-2.5 px-3 py-2.5 text-left text-sm transition-colors",
                  o.value === value
                    ? "bg-primary/10 font-medium text-primary"
                    : "text-foreground hover:bg-muted",
                )}
              >
                {o.label}
                {o.value === value && (
                  <CheckCircle2 className="ml-auto h-3.5 w-3.5 shrink-0 text-primary" />
                )}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ─── Step Indicator ──────────────────────────────────────────────────────────────

function StepIndicator({ currentStep }: { currentStep: WizardStep }) {
  return (
    <div className="flex items-center justify-center gap-0">
      {STEPS.map((s, i) => {
        const isActive = s.step === currentStep;
        const isCompleted = s.step < currentStep;
        return (
          <React.Fragment key={s.step}>
            {i > 0 && (
              <div
                className={cn(
                  "h-px w-8",
                  isCompleted ? "bg-primary" : "bg-border",
                )}
              />
            )}
            <div className="flex items-center gap-2">
              <div
                className={cn(
                  "flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold transition-colors",
                  isActive
                    ? "bg-primary text-primary-foreground"
                    : isCompleted
                      ? "bg-primary/20 text-primary"
                      : "bg-muted text-muted-foreground",
                )}
              >
                {isCompleted ? (
                  <CheckCircle2 className="h-4 w-4" />
                ) : (
                  s.step
                )}
              </div>
              <span
                className={cn(
                  "text-sm font-medium whitespace-nowrap",
                  isActive ? "text-primary" : "text-muted-foreground",
                )}
              >
                {s.label}
              </span>
            </div>
          </React.Fragment>
        );
      })}
    </div>
  );
}

// ─── Outline Tree ────────────────────────────────────────────────────────────────

let outlineIdCounter = 100;

function OutlineTree({
  items,
  onChange,
  depth = 0,
}: {
  items: OutlineItem[];
  onChange: (items: OutlineItem[]) => void;
  depth?: number;
}) {
  const addItem = (index: number) => {
    const newItems = [...items];
    const id = `o_new_${++outlineIdCounter}`;
    const chapterNum = newItems.length + 1;
    const prefix = depth === 0 ? `第${numberToChinese(chapterNum)}章 ` : `${chapterNum}.`;
    newItems.splice(index + 1, 0, { id, title: `${prefix}新章节`, children: [] });
    onChange(newItems);
  };

  const removeItem = (index: number) => {
    const newItems = items.filter((_, i) => i !== index);
    onChange(newItems);
  };

  const updateTitle = (index: number, title: string) => {
    const newItems = [...items];
    newItems[index] = { ...newItems[index]!, title };
    onChange(newItems);
  };

  const updateChildren = (index: number, children: OutlineItem[]) => {
    const newItems = [...items];
    newItems[index] = { ...newItems[index]!, children };
    onChange(newItems);
  };

  return (
    <div className="space-y-1">
      {items.map((item, index) => (
        <div key={item.id}>
          <div
            className={cn(
              "group flex items-center gap-2 rounded-lg px-3 py-2 transition-colors hover:bg-muted/50",
              depth > 0 && "ml-6",
            )}
          >
            <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
            <input
              type="text"
              value={item.title}
              onChange={(e) => updateTitle(index, e.target.value)}
              className="flex-1 bg-transparent text-sm text-foreground outline-none"
            />
            <button
              type="button"
              onClick={() => addItem(index)}
              className="shrink-0 rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-accent hover:text-foreground group-hover:opacity-100"
            >
              <Plus className="h-3.5 w-3.5" />
            </button>
            {items.length > 1 && (
              <button
                type="button"
                onClick={() => removeItem(index)}
                className="shrink-0 rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
          {item.children.length > 0 && (
            <OutlineTree
              items={item.children}
              onChange={(children) => updateChildren(index, children)}
              depth={depth + 1}
            />
          )}
        </div>
      ))}
    </div>
  );
}

function numberToChinese(n: number): string {
  const chars = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"];
  if (n <= 10) return chars[n] ?? String(n);
  if (n < 20) return "十" + (n % 10 === 0 ? "" : chars[n % 10]);
  return String(n);
}

// ─── Member Role Section ─────────────────────────────────────────────────────────

function MemberRoleSection({
  role,
  members,
  onAdd,
  onRemove,
}: {
  role: MemberRole;
  members: MockUser[];
  onAdd: (user: MockUser) => void;
  onRemove: (userId: string) => void;
}) {
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setDropdownOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const availableUsers = MOCK_USERS.filter(
    (u) => !members.some((m) => m.id === u.id),
  );

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-foreground">
          {MEMBER_ROLE_LABELS[role]}
        </span>
        <div ref={ref} className="relative">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="h-7 gap-1 text-xs text-muted-foreground"
          >
            <Plus className="h-3 w-3" />
            添加成员
          </Button>
          <AnimatePresence>
            {dropdownOpen && availableUsers.length > 0 && (
              <motion.div
                initial={{ opacity: 0, y: -4, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -4, scale: 0.98 }}
                transition={{ duration: 0.15 }}
                className="absolute right-0 top-full z-50 mt-1 min-w-[120px] overflow-hidden rounded-xl border border-border bg-background shadow-lg shadow-black/5"
              >
                {availableUsers.map((u) => (
                  <button
                    key={u.id}
                    type="button"
                    onClick={() => {
                      onAdd(u);
                      setDropdownOpen(false);
                    }}
                    className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-foreground transition-colors hover:bg-muted"
                  >
                    <UserCircle className="h-4 w-4 text-muted-foreground" />
                    {u.name}
                  </button>
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {members.length === 0 ? (
        <div className="flex items-center gap-2 rounded-lg border border-dashed border-border px-3 py-3 text-xs text-muted-foreground">
          <UserCircle className="h-4 w-4" />
          暂未分配成员
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          {members.map((m) => (
            <span
              key={m.id}
              className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-3 py-1 text-sm font-medium text-primary"
            >
              <UserCircle className="h-3.5 w-3.5" />
              {m.name}
              <button
                type="button"
                onClick={() => onRemove(m.id)}
                className="ml-0.5 rounded-full p-0.5 transition-colors hover:bg-primary/20"
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Slide Variants ──────────────────────────────────────────────────────────────

const slideVariants = {
  enter: (direction: number) => ({
    x: direction > 0 ? 60 : -60,
    opacity: 0,
  }),
  center: {
    x: 0,
    opacity: 1,
  },
  exit: (direction: number) => ({
    x: direction > 0 ? -60 : 60,
    opacity: 0,
  }),
};

// ─── Main Component ──────────────────────────────────────────────────────────────

export default function ProjectCreateWizard({
  open,
  onClose,
  onCreated,
}: ProjectCreateWizardProps) {
  // Step
  const [step, setStep] = useState<WizardStep>(1);
  const [direction, setDirection] = useState(1);

  // Step 1: Basic info
  const [name, setName] = useState("");
  const [reportType, setReportType] = useState<ReportType>("environmental_impact");
  const [client, setClient] = useState("");
  const [targetStandard, setTargetStandard] = useState("");

  // Step 2: Template
  const [templateId, setTemplateId] = useState("tpl_env");

  // Step 3: Outline
  const [outline, setOutline] = useState<OutlineItem[]>(
    DEFAULT_OUTLINES["environmental_impact"] ?? BLANK_OUTLINE,
  );

  // Step 4: Members
  const emptyMembers: Record<MemberRole, MockUser[]> = {
    manager: [],
    writer: [],
    reviewer: [],
    approver: [],
    issuer: [],
  };
  const [membersByRole, setMembersByRole] = useState<Record<MemberRole, MockUser[]>>(emptyMembers);

  // Submitting
  const [submitting, setSubmitting] = useState(false);

  // When report type changes, update outline if no template selected or blank template
  const handleReportTypeChange = useCallback((newType: string) => {
    setReportType(newType as ReportType);
    if (templateId === "tpl_blank" || !templateId) {
      setOutline(DEFAULT_OUTLINES[newType] ?? BLANK_OUTLINE);
    }
  }, [templateId]);

  // When template changes, update outline
  const handleTemplateChange = useCallback((newTemplateId: string) => {
    setTemplateId(newTemplateId);
    if (newTemplateId === "tpl_blank") {
      setOutline(BLANK_OUTLINE);
    } else {
      setOutline(DEFAULT_OUTLINES[reportType] ?? BLANK_OUTLINE);
    }
  }, [reportType]);

  // Navigation
  const goNext = () => {
    if (step === 1) {
      if (!name.trim()) { toast.error("请输入项目名称"); return; }
      if (!client.trim()) { toast.error("请输入客户名称"); return; }
    }
    if (step < 4) {
      setDirection(1);
      setStep((s) => (s + 1) as WizardStep);
    }
  };

  const goPrev = () => {
    if (step > 1) {
      setDirection(-1);
      setStep((s) => (s - 1) as WizardStep);
    }
  };

  // Submit
  const handleCreate = async () => {
    setSubmitting(true);
    try {
      const memberList = Object.entries(membersByRole).flatMap(([role, users]) =>
        users.map((u) => ({ userId: u.id, role: role as MemberRole })),
      );

      const project = await projectApi.create({
        name: name.trim(),
        reportType,
        client: client.trim(),
        targetStandard: targetStandard.trim() || undefined,
        templateId: templateId === "tpl_blank" ? undefined : templateId,
        members: memberList.length > 0 ? memberList : undefined,
      });

      toast.success("项目创建成功");
      onCreated(project);
      handleClose();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "项目创建失败";
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  // Reset & close
  const handleClose = () => {
    setStep(1);
    setName("");
    setReportType("environmental_impact");
    setClient("");
    setTargetStandard("");
    setTemplateId("tpl_env");
    setOutline(DEFAULT_OUTLINES["environmental_impact"] ?? BLANK_OUTLINE);
    setMembersByRole(emptyMembers);
    setSubmitting(false);
    onClose();
  };

  // Member operations
  const addMember = (role: MemberRole, user: MockUser) => {
    setMembersByRole((prev) => ({
      ...prev,
      [role]: [...prev[role], user],
    }));
  };

  const removeMember = (role: MemberRole, userId: string) => {
    setMembersByRole((prev) => ({
      ...prev,
      [role]: prev[role].filter((u) => u.id !== userId),
    }));
  };

  if (!open) return null;

  const selectedTemplate = MOCK_TEMPLATES.find((t) => t.id === templateId);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
          onClick={(e) => {
            if (e.target === e.currentTarget) handleClose();
          }}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 10 }}
            transition={{ duration: 0.2 }}
            className="flex w-full max-w-2xl max-h-[85vh] flex-col rounded-2xl bg-background shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex shrink-0 items-center justify-between border-b border-border px-6 py-4">
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-primary/20 to-primary/5">
                  <FileText className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-foreground">新建报告项目</h2>
                  <p className="text-xs text-muted-foreground">
                    步骤 {step} / 4 — {STEPS.find((s) => s.step === step)?.label}
                  </p>
                </div>
              </div>
              <button
                onClick={handleClose}
                className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Step Indicator */}
            <div className="shrink-0 border-b border-border px-6 py-3">
              <StepIndicator currentStep={step} />
            </div>

            {/* Body */}
            <div className="relative flex-1 overflow-y-auto px-6 py-5">
              <AnimatePresence mode="wait" custom={direction}>
                {/* Step 1: Basic Info */}
                {step === 1 && (
                  <motion.div
                    key="step1"
                    custom={direction}
                    variants={slideVariants}
                    initial="enter"
                    animate="center"
                    exit="exit"
                    transition={{ duration: 0.2 }}
                    className="space-y-5"
                  >
                    <div className="space-y-2">
                      <label className="text-sm font-medium text-foreground">
                        项目名称 <span className="text-destructive">*</span>
                      </label>
                      <Input
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        placeholder="请输入项目名称"
                      />
                    </div>

                    <div className="space-y-2">
                      <label className="text-sm font-medium text-foreground">
                        报告类型
                      </label>
                      <CustomSelect
                        value={reportType}
                        onChange={handleReportTypeChange}
                        options={REPORT_TYPE_OPTIONS}
                      />
                    </div>

                    <div className="space-y-2">
                      <label className="text-sm font-medium text-foreground">
                        客户 <span className="text-destructive">*</span>
                      </label>
                      <Input
                        value={client}
                        onChange={(e) => setClient(e.target.value)}
                        placeholder="请输入客户名称"
                      />
                    </div>

                    <div className="space-y-2">
                      <label className="text-sm font-medium text-foreground">
                        目标标准
                      </label>
                      <Input
                        value={targetStandard}
                        onChange={(e) => setTargetStandard(e.target.value)}
                        placeholder="如 HJ 2.1-2016（选填）"
                      />
                    </div>
                  </motion.div>
                )}

                {/* Step 2: Select Template */}
                {step === 2 && (
                  <motion.div
                    key="step2"
                    custom={direction}
                    variants={slideVariants}
                    initial="enter"
                    animate="center"
                    exit="exit"
                    transition={{ duration: 0.2 }}
                    className="space-y-3"
                  >
                    <p className="text-sm text-muted-foreground">
                      选择一个模板作为报告的基础结构
                    </p>
                    <div className="space-y-2">
                      {MOCK_TEMPLATES.map((tpl) => (
                        <label
                          key={tpl.id}
                          className={cn(
                            "flex cursor-pointer items-start gap-3 rounded-xl border-2 p-4 transition-all",
                            templateId === tpl.id
                              ? "border-primary bg-primary/5 shadow-sm"
                              : "border-border hover:border-primary/40 hover:bg-accent/50",
                          )}
                        >
                          <input
                            type="radio"
                            name="template"
                            value={tpl.id}
                            checked={templateId === tpl.id}
                            onChange={() => handleTemplateChange(tpl.id)}
                            className="sr-only"
                          />
                          <div
                            className={cn(
                              "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 transition-colors",
                              templateId === tpl.id
                                ? "border-primary bg-primary"
                                : "border-input bg-background",
                            )}
                          >
                            {templateId === tpl.id && (
                              <div className="h-2 w-2 rounded-full bg-primary-foreground" />
                            )}
                          </div>
                          <div className="min-w-0 flex-1">
                            <p
                              className={cn(
                                "text-sm font-medium",
                                templateId === tpl.id ? "text-primary" : "text-foreground",
                              )}
                            >
                              {tpl.name}
                            </p>
                            <p className="mt-1 text-xs text-muted-foreground">
                              {tpl.description}
                            </p>
                          </div>
                        </label>
                      ))}
                    </div>
                  </motion.div>
                )}

                {/* Step 3: Report Outline */}
                {step === 3 && (
                  <motion.div
                    key="step3"
                    custom={direction}
                    variants={slideVariants}
                    initial="enter"
                    animate="center"
                    exit="exit"
                    transition={{ duration: 0.2 }}
                    className="space-y-3"
                  >
                    <div className="flex items-center justify-between">
                      <p className="text-sm text-muted-foreground">
                        预览并编辑报告大纲结构
                      </p>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          const id = `o_new_${++outlineIdCounter}`;
                          const chapterNum = outline.length + 1;
                          setOutline([
                            ...outline,
                            { id, title: `第${numberToChinese(chapterNum)}章 新章节`, children: [] },
                          ]);
                        }}
                        className="h-7 gap-1 text-xs"
                      >
                        <Plus className="h-3 w-3" />
                        添加章节
                      </Button>
                    </div>
                    <div className="rounded-xl border border-border bg-muted/30 p-3">
                      <OutlineTree items={outline} onChange={setOutline} />
                    </div>
                  </motion.div>
                )}

                {/* Step 4: Member Assignment */}
                {step === 4 && (
                  <motion.div
                    key="step4"
                    custom={direction}
                    variants={slideVariants}
                    initial="enter"
                    animate="center"
                    exit="exit"
                    transition={{ duration: 0.2 }}
                    className="space-y-5"
                  >
                    <p className="text-sm text-muted-foreground">
                      为项目各角色分配团队成员
                    </p>
                    {MEMBER_ROLES.map((role) => (
                      <MemberRoleSection
                        key={role}
                        role={role}
                        members={membersByRole[role]}
                        onAdd={(user) => addMember(role, user)}
                        onRemove={(userId) => removeMember(role, userId)}
                      />
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* Footer */}
            <div className="flex shrink-0 items-center justify-between border-t border-border px-6 py-4">
              <Button type="button" variant="outline" onClick={handleClose}>
                取消
              </Button>

              <div className="flex gap-3">
                {step > 1 && (
                  <Button
                    type="button"
                    variant="outline"
                    onClick={goPrev}
                    className="gap-1"
                  >
                    <ChevronLeft className="h-4 w-4" />
                    上一步
                  </Button>
                )}

                {step < 4 ? (
                  <Button type="button" onClick={goNext} className="gap-1">
                    下一步
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                ) : (
                  <Button
                    type="button"
                    onClick={handleCreate}
                    disabled={submitting}
                    className="gap-1"
                  >
                    {submitting ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" />
                        创建中...
                      </>
                    ) : (
                      <>
                        <CheckCircle2 className="h-4 w-4" />
                        创建
                      </>
                    )}
                  </Button>
                )}
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
