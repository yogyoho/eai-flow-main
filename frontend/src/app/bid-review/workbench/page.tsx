"use client";
/**
 * /workbench 深链兼容重定向(Plan7,裁定8 工作台退役):→ /results?task_id=。
 * EAI-CUSTOM (2026-10-31): 旧书签/徽标链路保活;本路由不再承载内容。
 */
import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

export default function WorkbenchRedirectPage() {
  const router = useRouter();
  const sp = useSearchParams();
  useEffect(() => {
    const tid = sp.get("task_id");
    router.replace(
      tid
        ? `/bid-review/results?task_id=${encodeURIComponent(tid)}`
        : "/bid-review/results",
    );
  }, [router, sp]);
  return null;
}
