"use client";

// EAI-CUSTOM (2026-10-30): 规则效果看板路由(参照 docs/designs/2026-10-30-bid-review-ui.html #s10)。
// 导航入口与权限点(bid:page:rules,同治理域)在 app/bid-review/layout.tsx 注册——勿在此重复鉴权。
import { MetricsView } from "@/extensions/bid-review/components/MetricsView";

export default function BidReviewMetricsPage() {
  return <MetricsView />;
}
