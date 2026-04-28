"use client";

import { BarChart3, TrendingUp, AlertTriangle, Info } from "lucide-react";
import React from "react";
import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ResponsiveContainer,
} from "recharts";

import { cn } from "@/lib/utils";

const DIMENSIONS = [
  { name: "完整性", score: 92, status: "通过", color: "bg-emerald-500" },
  { name: "准确性", score: 85, status: "部分章节需人工校验", color: "bg-amber-500" },
  { name: "一致性", score: 98, status: "通过", color: "bg-emerald-500" },
  { name: "合规性", score: 94, status: "通过", color: "bg-emerald-500" },
  {
    name: "可用性",
    score: 87,
    status: "3 节缺少示例片段",
    color: "bg-amber-500",
  },
];

const RADAR_DATA = DIMENSIONS.map((d) => ({
  subject: d.name,
  A: d.score,
  fullMark: 100,
}));

const ISSUES = [
  {
    id: "1",
    type: "warning",
    title: "sec_04_02 水环境现状 - 缺少 RAG 数据源关联",
    suggestion: "建议: 关联「地表水环境质量标准」知识库",
    action: "一键修复",
  },
  {
    id: "2",
    type: "warning",
    title: "sec_07_03 风险预测 - 内容契约关键要素少于3个",
    suggestion: "当前: 2个  建议: ≥3个",
    action: "编辑修复",
  },
  {
    id: "3",
    type: "info",
    title: "sec_09_01 废气治理 - 示例片段超过1年未更新",
    suggestion: "最后更新: 2025-02-15",
    action: "更新示例",
  },
];

export default function QualityAssessment() {
  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex justify-between items-center p-4 border-b border-border bg-card shrink-0">
        <h2 className="text-lg font-semibold flex items-center gap-2 text-foreground tracking-tight">
          <BarChart3 className="w-5 h-5 text-primary" />
          知识质量评估
        </h2>
        <div className="flex gap-2">
          <button className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors shadow-sm font-medium text-sm">
            <TrendingUp className="w-4 h-4" /> 生成报告
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6 space-y-8 bg-muted/30">
        {/* Score Cards */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Overall Score */}
          <div className="lg:col-span-1 bg-card p-8 rounded-xl border border-border shadow-sm flex flex-col items-center justify-center text-center space-y-4">
            <h3 className="text-sm font-bold text-muted-foreground uppercase tracking-widest">
              整体评分
            </h3>
            <div className="relative w-48 h-48 flex items-center justify-center">
              <div className="absolute inset-0 rounded-full border-8 border-muted" />
              <div
                className="absolute inset-0 rounded-full border-8 border-primary"
                style={{
                  clipPath: "polygon(0 0, 100% 0, 100% 92%, 0 92%)",
                }}
              />
              <div className="text-center">
                <div className="text-5xl font-black text-foreground">4.6</div>
                <div className="text-sm text-muted-foreground font-bold">/ 5.0</div>
              </div>
            </div>
            <div className="bg-emerald-50 text-emerald-600 border border-emerald-100 px-4 py-1 rounded-full font-medium text-sm">
              优秀
            </div>
            <p className="text-sm text-muted-foreground">
              模板质量稳定，合规性极高
            </p>
          </div>

          {/* Dimension Scores */}
          <div className="lg:col-span-2 bg-card p-8 rounded-xl border border-border shadow-sm">
            <div className="flex justify-between items-start mb-6">
              <h3 className="text-lg font-semibold text-foreground">
                维度评分
              </h3>
              <div className="h-48 w-48">
                <ResponsiveContainer width="100%" height="100%">
                  <RadarChart cx="50%" cy="50%" outerRadius="80%" data={RADAR_DATA}>
                    <PolarGrid stroke="#e4e4e7" />
                    <PolarAngleAxis
                      dataKey="subject"
                      tick={{ fill: "#a1a1aa", fontSize: 10 }}
                    />
                    <PolarRadiusAxis angle={30} domain={[0, 100]} />
                    <Radar
                      name="Score"
                      dataKey="A"
                      stroke="#4f46e5"
                      fill="#4f46e5"
                      fillOpacity={0.2}
                    />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div className="space-y-4">
              {DIMENSIONS.map((dim, i) => (
                <div key={i} className="space-y-1.5">
                  <div className="flex justify-between text-sm font-medium">
                    <span className="text-foreground">{dim.name}</span>
                    <span className="text-muted-foreground">{dim.score}%</span>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                      <div
                        className={cn(
                          "h-full rounded-full transition-all duration-1000",
                          dim.color
                        )}
                        style={{ width: `${dim.score}%` }}
                      />
                    </div>
                    <span className="text-xs text-muted-foreground whitespace-nowrap min-w-[120px]">
                      {dim.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Issue List */}
        <div className="space-y-4">
          <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-amber-500" /> 问题清单
          </h3>
          <div className="space-y-3">
            {ISSUES.map((issue) => (
              <div
                key={issue.id}
                className="bg-card p-5 rounded-xl border border-border shadow-sm hover:border-primary/30 hover:shadow-md transition-all flex justify-between items-center group"
              >
                <div className="flex gap-4">
                  <div
                    className={cn(
                      "w-10 h-10 rounded-lg flex items-center justify-center",
                      issue.type === "warning"
                        ? "bg-amber-50 text-amber-600"
                        : "bg-blue-50 text-blue-600"
                    )}
                  >
                    {issue.type === "warning" ? (
                      <AlertTriangle className="w-5 h-5" />
                    ) : (
                      <Info className="w-5 h-5" />
                    )}
                  </div>
                  <div className="space-y-1">
                    <h4 className="font-bold text-foreground">{issue.title}</h4>
                    <p className="text-sm text-muted-foreground">
                      {issue.suggestion}
                    </p>
                  </div>
                </div>
                <div className="flex gap-3">
                  <button className="px-4 py-1.5 bg-secondary text-primary rounded-lg text-sm font-medium hover:bg-secondary/80 transition-colors">
                    {issue.action}
                  </button>
                  <button className="px-4 py-1.5 text-muted-foreground hover:text-foreground rounded-lg text-sm font-medium transition-colors">
                    忽略
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
