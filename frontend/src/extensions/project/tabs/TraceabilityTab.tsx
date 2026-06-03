"use client";

import {
  AlertTriangle,
  BookOpen,
  Database,
  FileText,
  Globe,
  Lightbulb,
  Link2,
  Loader2,
  Search,
  Shield,
  User,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import type { ProjectChapter, ReportProject } from "@/extensions/project/types";
import type { ProjectIdentity } from "@/extensions/project/tabRegistry";
import { workflowApi } from "@/extensions/workflow/api";

interface TraceabilityTabProps {
  project: ReportProject;
  projectId: string;
  onRefresh: () => void;
  identity: ProjectIdentity | null;
}

interface SourceEntry {
  id: string;
  sourceType: string;
  sourceRef: string | null;
  snippet: string | null;
  confidence: number | null;
}

interface ChapterSourceData {
  sources: SourceEntry[];
  stats: Record<string, number>;
  missingCount: number;
}

const SOURCE_TYPE_CONFIG: Record<string, { label: string; color: string; icon: any }> = {
  rag_retrieval: { label: "RAG 检索", color: "bg-blue-50 text-blue-700 border-blue-200", icon: Search },
  knowledge_base: { label: "知识库", color: "bg-cyan-50 text-cyan-700 border-cyan-200", icon: Database },
  regulation: { label: "法规标准", color: "bg-emerald-50 text-emerald-700 border-emerald-200", icon: Shield },
  ai_generated: { label: "AI 生成", color: "bg-amber-50 text-amber-700 border-amber-200", icon: Lightbulb },
  human_written: { label: "人工撰写", color: "bg-purple-50 text-purple-700 border-purple-200", icon: User },
  template: { label: "模板", color: "bg-gray-50 text-gray-700 border-gray-200", icon: FileText },
  external_data: { label: "外部数据", color: "bg-teal-50 text-teal-700 border-teal-200", icon: Globe },
  web: { label: "网页引用", color: "bg-sky-50 text-sky-700 border-sky-200", icon: Link2 },
};

function flattenChapters(chapters: ProjectChapter[]): ProjectChapter[] {
  const result: ProjectChapter[] = [];
  for (const ch of chapters) {
    result.push(ch);
    if (ch.children?.length) result.push(...flattenChapters(ch.children));
  }
  return result;
}

export function TraceabilityTab({ project, projectId }: TraceabilityTabProps) {
  const [chapterData, setChapterData] = useState<Map<string, ChapterSourceData>>(new Map());
  const [loading, setLoading] = useState(true);
  const [selectedChapterId, setSelectedChapterId] = useState<string | null>(null);

  const flatChapters = flattenChapters(project.chapters ?? []);

  const loadData = useCallback(async () => {
    if (!flatChapters.length) {
      setLoading(false);
      return;
    }
    try {
      setLoading(true);
      const dataMap = new Map<string, ChapterSourceData>();
      await Promise.all(
        flatChapters.map(async (ch) => {
          try {
            const [sourceResult, missingResult] = await Promise.all([
              workflowApi.getSources(projectId, ch.id).catch(() => ({ sources: [], stats: {} })),
              workflowApi.getMissingSources(projectId, ch.id).catch(() => ({ missing: [] })),
            ]);
            dataMap.set(ch.id, {
              sources: sourceResult.sources ?? [],
              stats: sourceResult.stats ?? {},
              missingCount: missingResult.missing?.length ?? 0,
            });
          } catch {
            dataMap.set(ch.id, { sources: [], stats: {}, missingCount: 0 });
          }
        }),
      );
      setChapterData(dataMap);
    } finally {
      setLoading(false);
    }
  }, [projectId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Aggregate stats
  const aggregated = new Map<string, number>();
  let totalSources = 0;
  let totalMissing = 0;
  for (const [, data] of chapterData) {
    for (const [type, count] of Object.entries(data.stats)) {
      aggregated.set(type, (aggregated.get(type) ?? 0) + count);
    }
    totalSources += data.sources.length;
    totalMissing += data.missingCount;
  }

  const selectedData = selectedChapterId ? chapterData.get(selectedChapterId) : null;

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {/* Summary Cards */}
      <div className="border-b border-border/40 px-5 py-3 shrink-0">
        <div className="flex items-center gap-3 flex-wrap">
          {Array.from(aggregated.entries())
            .sort((a, b) => b[1] - a[1])
            .map(([type, count]) => {
              const cfg = SOURCE_TYPE_CONFIG[type] ?? {
                label: type,
                color: "bg-gray-50 text-gray-700 border-gray-200",
                icon: FileText,
              };
              const Icon = cfg.icon;
              return (
                <div
                  key={type}
                  className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 ${cfg.color}`}
                >
                  <Icon className="h-3.5 w-3.5" />
                  <span className="text-[12px] font-medium">{cfg.label}</span>
                  <Badge variant="secondary" className="ml-0.5 h-4 min-w-[20px] justify-center text-[10px]">
                    {count}
                  </Badge>
                </div>
              );
            })}
          {totalSources === 0 && (
            <p className="text-sm text-muted-foreground">暂无溯源数据</p>
          )}
        </div>
      </div>

      {/* Two-column content */}
      <div className="flex flex-1 min-h-0">
        {/* Chapter Tree */}
        <div className="w-[300px] shrink-0 border-r border-border/40">
          <ScrollArea className="h-full">
            <div className="p-3 space-y-0.5">
              {flatChapters.map((ch) => {
                const data = chapterData.get(ch.id);
                const sourceCount = data?.sources.length ?? 0;
                const missingCount = data?.missingCount ?? 0;
                return (
                  <button
                    key={ch.id}
                    type="button"
                    onClick={() => setSelectedChapterId(ch.id)}
                    className={`w-full text-left rounded-lg px-3 py-2.5 transition-all ${
                      selectedChapterId === ch.id
                        ? "bg-primary/5 ring-1 ring-primary/20"
                        : "hover:bg-accent/40"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                      <span className="flex-1 truncate text-[13px] text-foreground">{ch.title}</span>
                      {sourceCount > 0 && (
                        <Badge variant="secondary" className="text-[10px] h-4 px-1.5">
                          {sourceCount}
                        </Badge>
                      )}
                      {missingCount > 0 && (
                        <Badge
                          variant="outline"
                          className="text-[10px] h-4 px-1.5 border-red-300 text-red-600 bg-red-50"
                        >
                          <AlertTriangle className="h-2.5 w-2.5 mr-0.5" />
                          {missingCount}
                        </Badge>
                      )}
                    </div>
                  </button>
                );
              })}
            </div>
          </ScrollArea>
        </div>

        {/* Source Detail */}
        <div className="flex-1 min-w-0">
          {selectedData ? (
            <ScrollArea className="h-full">
              <div className="p-5 space-y-4">
                {/* Missing sources alert */}
                {selectedData.missingCount > 0 && (
                  <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-3">
                    <AlertTriangle className="h-4 w-4 text-red-600 shrink-0 mt-0.5" />
                    <div>
                      <p className="text-sm font-medium text-red-800">
                        发现 {selectedData.missingCount} 处缺失引用
                      </p>
                      <p className="text-xs text-red-600/80 mt-0.5">部分内容缺少来源标注，建议补充引用信息</p>
                    </div>
                  </div>
                )}

                {/* Source stats for this chapter */}
                {Object.keys(selectedData.stats).length > 0 && (
                  <div className="flex items-center gap-2 flex-wrap">
                    {Object.entries(selectedData.stats).map(([type, count]) => {
                      const cfg = SOURCE_TYPE_CONFIG[type] ?? { label: type, color: "bg-gray-50 text-gray-700" };
                      return (
                        <Badge key={type} variant="outline" className={`${cfg.color} text-[11px]`}>
                          {cfg.label}: {count}
                        </Badge>
                      );
                    })}
                  </div>
                )}

                {/* Source list */}
                {selectedData.sources.length > 0 ? (
                  <div className="space-y-2">
                    {selectedData.sources.map((source, idx) => {
                      const cfg = SOURCE_TYPE_CONFIG[source.sourceType] ?? {
                        label: source.sourceType,
                        color: "bg-gray-50 text-gray-700 border-gray-200",
                        icon: FileText,
                      };
                      const Icon = cfg.icon;
                      return (
                        <div
                          key={source.id ?? idx}
                          className="rounded-lg border border-border/40 p-3 hover:bg-accent/20 transition-colors"
                        >
                          <div className="flex items-center gap-2 mb-1">
                            <Icon className="h-3.5 w-3.5 text-muted-foreground" />
                            <Badge variant="outline" className={`text-[10px] ${cfg.color}`}>
                              {cfg.label}
                            </Badge>
                            {source.confidence != null && (
                              <span className="text-[10px] text-muted-foreground">
                                置信度: {Math.round(source.confidence * 100)}%
                              </span>
                            )}
                          </div>
                          {source.sourceRef && (
                            <p className="text-[11px] text-muted-foreground font-mono mt-0.5">{source.sourceRef}</p>
                          )}
                          {source.snippet && (
                            <p className="text-sm text-foreground mt-1.5 leading-relaxed">{source.snippet}</p>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center py-12">
                    <BookOpen className="h-8 w-8 text-muted-foreground/25 mb-2" />
                    <p className="text-sm text-muted-foreground">该章节暂无溯源数据</p>
                  </div>
                )}
              </div>
            </ScrollArea>
          ) : (
            <div className="flex h-full items-center justify-center">
              <div className="text-center">
                <Link2 className="h-8 w-8 text-muted-foreground/25 mx-auto mb-2" />
                <p className="text-sm text-muted-foreground">选择左侧章节查看溯源详情</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
