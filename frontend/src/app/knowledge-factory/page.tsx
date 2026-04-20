"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { ShellLayout } from "@/extensions/shell";
import type { TabId } from "@/extensions/knowledge-factory/types";
import {
  SampleReports,
  TemplateExtraction,
  TemplateEditor,
  LawLibrary,
  RuleEngine,
  VersionControl,
  QualityAssessment,
  WebScraper,
} from "@/extensions/knowledge-factory";
import { cn } from "@/lib/utils";

const NAV_ITEMS: { id: TabId; label: string }[] = [
  { id: "reports", label: "样例管理" },
  { id: "extraction", label: "模板抽取" },
  { id: "editor", label: "模板编辑" },
  { id: "law", label: "法规标准" },
  { id: "rules", label: "合规规则" },
  { id: "version", label: "版本管理" },
  { id: "quality", label: "质量评估" },
  { id: "scraper", label: "网页爬取" },
];

const TAB_COMPONENTS: Record<TabId, React.ComponentType> = {
  reports: SampleReports,
  extraction: TemplateExtraction,
  editor: TemplateEditor,
  law: LawLibrary,
  rules: RuleEngine,
  version: VersionControl,
  quality: QualityAssessment,
  scraper: WebScraper,
};

function KnowledgeFactoryLayoutContent({ children }: { children: React.ReactNode }) {
  const params = useSearchParams();
  const currentTab = (params.get("tab") ?? "reports") as TabId;

  return (
    <ShellLayout>
      <div className="flex flex-col h-full bg-muted">
        {/* 顶部导航栏 — 与 admin/layout.tsx 一致 */}
        <header className="bg-background border-b border-border h-16 flex items-center px-6 shrink-0">
          <span className="font-bold text-lg tracking-tight text-foreground mr-8">知识工厂</span>
          <nav className="flex items-center gap-6 text-sm font-medium text-muted-foreground h-full">
            {NAV_ITEMS.map(({ id, label }) => {
              const href = `/knowledge-factory?tab=${id}`;
              const isActive = currentTab === id;
              return (
                <Link
                  key={id}
                  href={href}
                  className={cn(
                    "flex items-center h-full transition-colors py-5 border-b-2",
                    isActive
                      ? "text-primary border-primary"
                      : "border-transparent hover:text-foreground"
                  )}
                >
                  {label}
                </Link>
              );
            })}
          </nav>
        </header>

        {/* 主内容区 */}
        <div className="flex-1 overflow-hidden min-w-0 min-h-0">{children}</div>
      </div>
    </ShellLayout>
  );
}

function KnowledgeFactoryLayoutFallback({ children }: { children: React.ReactNode }) {
  return (
    <ShellLayout>
      <div className="flex flex-col h-full bg-muted">
        <header className="bg-background border-b border-border h-16 flex items-center px-6 shrink-0">
          <span className="font-bold text-lg tracking-tight text-foreground mr-8">知识工厂</span>
        </header>
        <div className="flex-1 overflow-hidden min-w-0 min-h-0">{children}</div>
      </div>
    </ShellLayout>
  );
}

function KnowledgeFactoryContent() {
  const params = useSearchParams();
  const tab = (params.get("tab") ?? "reports") as TabId;

  const Content = TAB_COMPONENTS[tab];
  return <Content />;
}

function KnowledgeFactoryRoute() {
  return (
    <Suspense fallback={<KnowledgeFactoryLayoutFallback><div className="flex items-center justify-center h-full text-muted-foreground text-sm">加载中...</div></KnowledgeFactoryLayoutFallback>}>
      <KnowledgeFactoryLayoutContent>
        <Suspense fallback={<div className="flex items-center justify-center h-full text-muted-foreground text-sm">加载中...</div>}>
          <KnowledgeFactoryContent />
        </Suspense>
      </KnowledgeFactoryLayoutContent>
    </Suspense>
  );
}

export default function KnowledgeFactoryPage() {
  return <KnowledgeFactoryRoute />;
}
