"use client";

// EAI-CUSTOM (2026-11-01 B10): 版本差异整屏路由(参照 docs/designs/2026-10-30-bid-review-ui.html #s8)。
// 导航入口与权限点(bid:page:results,同 results 域)在 app/bid-review/layout.tsx 注册。
import { DiffView } from "@/extensions/bid-review/components/DiffView";

export default function BidReviewDiffPage() {
  return <DiffView />;
}
