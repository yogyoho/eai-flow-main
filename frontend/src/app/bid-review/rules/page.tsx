"use client";

// M5 §4.7:RulesView 消费 useSearchParams(?rule= 深链,FAIL 行互跳②)——预渲染要求 Suspense 边界。
import { Suspense } from "react";

import { RulesView } from "@/extensions/bid-review/components/RulesView";

export default function BidReviewRulesPage() {
  return (
    <Suspense fallback={null}>
      <RulesView />
    </Suspense>
  );
}
