"use client";

import { Factory } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { Toaster } from "@/components/ui/sonner";
import { usePermission } from "@/core/permissions";
import {
  SampleReports,
  TemplateExtraction,
  TemplateEditor,
  LawLibrary,
  RuleEngine,
  VersionControl,
  QualityAssessment,
  WebScraper,
  BusinessDictionary,
} from "@/extensions/knowledge-factory";
import type { TabId } from "@/extensions/knowledge-factory/types";
import { ShellLayout } from "@/extensions/shell";
import { cn } from "@/lib/utils";

// EAI-CUSTOM: 每个 tab 映射到子页面权限点（/api/permissions/me 的 pages），供 canPage 过滤
const NAV_ITEMS: { id: TabId; label: string; pageId: string }[] = [
  { id: "reports", label: "样例管理", pageId: "kf:page:sample" },
  { id: "extraction", label: "模板抽取", pageId: "kf:page:extraction" },
  { id: "editor", label: "模板编辑", pageId: "kf:page:template" },
  { id: "law", label: "法规标准", pageId: "kf:page:law" },
  { id: "rules", label: "合规规则", pageId: "kf:page:compliance" },
  { id: "version", label: "版本管理", pageId: "kf:page:version" },
  { id: "quality", label: "质量评估", pageId: "kf:page:quality" },
  { id: "scraper", label: "网页爬取", pageId: "kf:page:scrape" },
  { id: "dictionaries", label: "业务字典", pageId: "kf:page:dict" },
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
  dictionaries: BusinessDictionary,
};

// EAI-CUSTOM: 主内容区。usePermission 必须在 ShellLayout 的 PermissionProvider 内部调用，
// 因此把顶部导航 + tab 内容渲染下沉到 ShellLayout 的 children 中（本组件即其 children）。
function KnowledgeFactoryMain() {
  const params = useSearchParams();
  const { canPage, isLoading: permLoading } = usePermission();
  // 权限加载中 fail-open 全显，加载完成后按 canPage(pageId) 过滤不可见 tab
  const visibleNav = permLoading ? NAV_ITEMS : NAV_ITEMS.filter((n) => canPage(n.pageId));
  const rawTab = (params.get("tab") ?? "reports") as TabId;
  // URL 指定的 tab 无权限时，回退到第一个可见 tab
  const currentTab = visibleNav.some((n) => n.id === rawTab) ? rawTab : (visibleNav[0]?.id ?? "reports");
  const Content = TAB_COMPONENTS[currentTab];

  return (
    <div className="flex flex-col h-full bg-muted">
      {/* 顶部导航栏 — 与 admin/layout.tsx 一致 */}
      <header className="bg-background border-b border-border h-15 flex items-center px-6 shrink-0">
        <div className="p-1 border rounded-sm bg-amber-50 border-amber-200 text-amber-600 shrink-0 mr-3">
          <Factory className="w-4 h-4" />
        </div>
        <span className="font-bold text-lg tracking-tight text-foreground mr-8">知识工厂</span>
        <nav className="flex items-center gap-6 text-sm font-medium text-muted-foreground h-full">
          {visibleNav.map(({ id, label }) => {
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
      <div className="flex-1 overflow-hidden min-w-0 min-h-0 bg-background">
        <Suspense fallback={<div className="flex items-center justify-center h-full text-muted-foreground text-sm">加载中...</div>}>
          <Content />
        </Suspense>
      </div>
    </div>
  );
}

function KnowledgeFactoryLayoutContent() {
  return (
    <ShellLayout>
      <KnowledgeFactoryMain />
    </ShellLayout>
  );
}

function KnowledgeFactoryLayoutFallback({ children }: { children: React.ReactNode }) {
  return (
    <ShellLayout>
      <div className="flex flex-col h-full bg-muted">
        <header className="bg-background border-b border-border h-15 flex items-center px-6 shrink-0">
          <div className="p-1 border rounded-sm bg-amber-50 border-amber-200 text-amber-600 shrink-0 mr-3">
            <Factory className="w-4 h-4" />
          </div>
          <span className="font-bold text-lg tracking-tight text-foreground mr-8">知识工厂</span>
        </header>
        <div className="flex-1 overflow-hidden min-w-0 min-h-0 bg-background">{children}</div>
      </div>
    </ShellLayout>
  );
}

function KnowledgeFactoryRoute() {
  return (
    <>
    <Suspense fallback={<KnowledgeFactoryLayoutFallback><div className="flex items-center justify-center h-full text-muted-foreground text-sm">加载中...</div></KnowledgeFactoryLayoutFallback>}>
      <KnowledgeFactoryLayoutContent />
    </Suspense>
    <Toaster />
    </>
  );
}

export default function KnowledgeFactoryPage() {
  return <KnowledgeFactoryRoute />;
}
