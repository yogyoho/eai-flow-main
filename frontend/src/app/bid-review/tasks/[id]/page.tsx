import { redirect } from "next/navigation";

/**
 * 深链兼容重定向:/bid-review/tasks/{id} → /bid-review/results?task_id={id}。
 * TasksView(行点击 + 『查看结果』链)历史目标即本路径;结果页原为
 * /bid-review/workbench(审查工作台),Plan7(裁定8)退役工作台后本 shim
 * 直指 /bid-review/results?task_id=。EAI-CUSTOM (2026-10-31)。
 */
export default async function BidReviewTaskRedirectPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  redirect(`/bid-review/results?task_id=${encodeURIComponent(id)}`);
}
