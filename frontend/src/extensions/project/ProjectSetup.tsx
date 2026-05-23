"use client";

import { ArrowRight, Loader2 } from "lucide-react";
import { useCallback, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { projectApi } from "@/extensions/project/api";
import { REPORT_TYPE_LABELS, type ReportType, type ReportProject } from "@/extensions/project/types";
import { toast } from "sonner";

interface ProjectSetupProps {
  projectId?: string;
  onCreated?: (project: ReportProject) => void;
}

export function ProjectSetup({ projectId, onCreated }: ProjectSetupProps) {
  const [name, setName] = useState("");
  const [reportType, setReportType] = useState<ReportType | "">("");
  const [templateId, setTemplateId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = useCallback(async () => {
    if (!name.trim()) {
      toast.error("请输入项目名称");
      return;
    }
    if (!reportType) {
      toast.error("请选择报告类型");
      return;
    }
    setSubmitting(true);
    try {
      const project = await projectApi.create({
        name: name.trim(),
        reportType,
        templateId,
      });
      toast.success("项目创建成功");
      onCreated?.(project);
    } catch (err) {
      const message = err instanceof Error ? err.message : "创建项目失败";
      toast.error(message);
    } finally {
      setSubmitting(false);
    }
  }, [name, reportType, templateId, onCreated]);

  return (
    <div className="flex flex-col items-center justify-center flex-1 p-6">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center">
          <h2 className="text-2xl font-bold tracking-tight text-foreground">创建报告项目</h2>
          <p className="text-sm text-muted-foreground mt-1">填写基本信息，开始报告编写流程</p>
        </div>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="project-name">项目名称</Label>
            <Input
              id="project-name"
              placeholder="请输入项目名称"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="report-type">报告类型</Label>
            <Select value={reportType} onValueChange={(v) => setReportType(v as ReportType)}>
              <SelectTrigger id="report-type">
                <SelectValue placeholder="请选择报告类型" />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(REPORT_TYPE_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <Button
          className="w-full gap-2"
          onClick={handleSubmit}
          disabled={submitting || !name.trim() || !reportType}
        >
          {submitting ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <ArrowRight className="h-4 w-4" />
          )}
          创建项目并进入大纲
        </Button>
      </div>
    </div>
  );
}