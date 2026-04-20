"use client";

import {
  GitBranch,
  History,
  Plus,
  GitCommit,
  Tag,
  ArrowUpCircle,
  RotateCcw,
  Layout,
} from "lucide-react";
import React from "react";

import type { VersionHistory } from "@/extensions/knowledge-factory/types";
import { cn } from "@/lib/utils";

const MOCK_HISTORY: VersionHistory[] = [
  {
    version: "v3.2",
    date: "2026-03-20",
    author: "张三",
    comment: "更新第4章环境质量现状",
    changes: "+12节 -3节 修改 8 节内容契约",
    isHead: true,
  },
  {
    version: "v3.1",
    date: "2026-03-15",
    author: "李四",
    comment: "添加跨章节校验规则",
    changes: "+5条合规规则",
  },
  {
    version: "v3.0",
    date: "2026-03-01",
    author: "王五",
    comment: "重大版本更新",
    changes: "适配 HJ 2.4-2025 新导则",
  },
  {
    version: "v2.8",
    date: "2026-02-10",
    author: "张三",
    comment: "修复模板抽取bug",
    changes: "修复 sec_07_03 内容契约缺失",
  },
  {
    version: "v2.0-stable",
    date: "2025-12-01",
    author: "系统",
    comment: "稳定版本标记",
    changes: "初始稳定版本",
    isStable: true,
  },
];

export default function VersionControl() {
  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex justify-between items-center p-4 border-b border-border bg-card shrink-0">
        <h2 className="text-lg font-semibold flex items-center gap-2 text-foreground tracking-tight">
          <GitBranch className="w-5 h-5 text-primary" />
          模板版本管理
        </h2>
        <div className="flex gap-2">
          <button className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors shadow-sm font-medium text-sm">
            <Plus className="w-4 h-4" /> 新建分支
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6 space-y-8 bg-muted/30">
        {/* Version History */}
        <div className="bg-card rounded-xl border border-border shadow-sm overflow-hidden">
          <div className="p-4 border-b border-border bg-muted/50 flex items-center gap-2">
            <History className="w-5 h-5 text-muted-foreground" />
            <h3 className="font-semibold text-foreground">版本历史</h3>
          </div>
          <div className="p-6 relative">
            <div className="absolute left-9 top-6 bottom-6 w-0.5 bg-border" />
            <div className="space-y-8">
              {MOCK_HISTORY.map((item, i) => (
                <div key={i} className="relative pl-12">
                  <div
                    className={cn(
                      "absolute left-0 top-1.5 w-6 h-6 rounded-full border-2 bg-card z-10 flex items-center justify-center",
                      item.isHead
                        ? "border-primary"
                        : item.isStable
                          ? "border-emerald-600"
                          : "border-muted-foreground"
                    )}
                  >
                    {item.isStable ? (
                      <Tag className="w-3 h-3 text-emerald-600" />
                    ) : (
                      <GitCommit
                        className={cn(
                          "w-3 h-3",
                          item.isHead ? "text-primary" : "text-muted-foreground"
                        )}
                      />
                    )}
                  </div>

                  <div className="bg-card p-4 rounded-xl border border-border shadow-sm hover:border-primary/30 hover:shadow-md transition-all group">
                    <div className="flex justify-between items-start mb-2">
                      <div className="flex items-center gap-3">
                        <span
                          className={cn(
                            "font-mono font-bold text-sm",
                            item.isHead ? "text-primary" : "text-foreground"
                          )}
                        >
                          {item.isHead && "(HEAD) "}
                          {item.version}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {item.date}
                        </span>
                        <span className="text-xs bg-muted px-2 py-0.5 rounded text-muted-foreground">
                          {item.author}
                        </span>
                      </div>
                      <div className="flex gap-3 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button className="text-primary text-xs font-medium hover:text-primary/70 hover:underline transition-colors">
                          对比
                        </button>
                        <button className="text-primary text-xs font-medium hover:text-primary/70 hover:underline flex items-center gap-1 transition-colors">
                          <RotateCcw className="w-3 h-3" /> 回滚
                        </button>
                        {item.isHead && (
                          <button className="text-primary text-xs font-medium hover:text-primary/70 hover:underline flex items-center gap-1 transition-colors">
                            <ArrowUpCircle className="w-3 h-3" /> 部署到生产
                          </button>
                        )}
                      </div>
                    </div>
                    <p className="text-sm text-foreground font-medium">
                      {item.comment}
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      变更: {item.changes}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Branch Management */}
        <div className="space-y-4">
          <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
            <Layout className="w-5 h-5 text-primary" /> 分支管理
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {[
              {
                name: "main",
                label: "生产分支",
                version: "v3.2",
                color: "text-emerald-600",
              },
              {
                name: "dev",
                label: "开发分支",
                version: "v3.3-beta",
                color: "text-blue-600",
              },
              {
                name: "feature-ai",
                label: "新功能测试",
                version: "v3.3-ai",
                color: "text-purple-600",
              },
            ].map((branch, i) => (
              <div
                key={i}
                className="bg-card p-5 rounded-xl border border-border shadow-sm hover:border-primary/30 hover:shadow-md transition-all group"
              >
                <div className="flex items-center gap-2 mb-3">
                  <GitBranch className={cn("w-4 h-4", branch.color)} />
                  <span className="font-bold text-foreground">{branch.name}</span>
                </div>
                <div className="text-xs text-muted-foreground mb-1">
                  {branch.label}
                </div>
                <div className="text-lg font-mono font-bold text-foreground mb-4">
                  {branch.version}
                </div>
                <button className="w-full py-2 text-foreground bg-card border border-border rounded-lg text-sm font-medium hover:bg-accent transition-colors shadow-sm">
                  切换
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
