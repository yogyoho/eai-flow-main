"use client";

// EAI-CUSTOM (Plan 4, spec 2026-09-06 §2.4): 投标资料管理——应用中心独立应用薄壳。
// 镜像 coal-eia-samples/page.tsx 形态；后端 /api/extensions/bid-materials/*（Plan 1 已落地），
// 页面可见性由 permissions.yaml bid_materials 块(nav:bid-materials)+导航引擎驱动，前端不重复设卡。
import { Suspense } from "react";

import { BidMaterials } from "@/extensions/bid-materials";
import { ShellLayout } from "@/extensions/shell";

export default function BidMaterialsRoute() {
  return (
    <ShellLayout>
      <Suspense
        fallback={
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            加载中...
          </div>
        }
      >
        <BidMaterials />
      </Suspense>
    </ShellLayout>
  );
}
