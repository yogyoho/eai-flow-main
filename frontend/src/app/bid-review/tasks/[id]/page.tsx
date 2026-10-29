import { redirect } from "next/navigation";

/**
 * 深链兼容重定向:/bid-review/tasks/{id} → /bid-review/workbench?task_id={id}。
 * TasksView(行点击 + 『查看工作台』链)历史目标即本路径,而工作台真实地址是
 * /bid-review/workbench?task_id=(Task 17 落地);此 shim 保旧深链不断(bid-review
 * 修复轮 2026-10-29)。TasksView 本体不在修复轮授权文件清单内,故以重定向页替代改链。
 */
export default async function BidReviewTaskRedirectPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  redirect(`/bid-review/workbench?task_id=${encodeURIComponent(id)}`);
}
