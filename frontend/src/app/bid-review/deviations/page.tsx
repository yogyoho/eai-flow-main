"use client";

// EAI-CUSTOM (2026-11-01 B9): 响应偏离表路由(参照 docs/designs/2026-10-30-bid-review-ui.html #s7)。
// 导航入口与权限点(bid:page:results,同 results 域——先例=review 挂宿主页)在
// app/bid-review/layout.tsx 注册——勿在此重复鉴权。
import { DeviationsView } from "@/extensions/bid-review/components/DeviationsView";

export default function BidReviewDeviationsPage() {
  return <DeviationsView />;
}
