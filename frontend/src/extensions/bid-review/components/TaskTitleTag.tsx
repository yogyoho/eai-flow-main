/**
 * 页头任务号(2026-10-31 用户定案:选中任务编号不进侧栏,随各页页头主标题右侧
 * 展示,习语=原型「审查结果 · TBR-2026-0309」;spec §3.2 选中任务模型)。
 * taskId 为空(零任务/未加载)时零渲染。四个任务链页 h2 统一消费;B1 biz_no
 * 落地后此处换业务号。
 */
export function TaskTitleTag({
  taskId,
}: {
  taskId: string | null | undefined;
}) {
  if (!taskId) return null;
  // 原型 h2 内任务号=纯正文(同字号/字重/色,非 mono);tt-id 仅作语义钩子
  return <span className="tt-id">{" · "}{taskId.slice(0, 8)}</span>;
}
