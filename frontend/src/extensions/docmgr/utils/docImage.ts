// EAI-CUSTOM: 上传图片到个人文档线程目录（BlockNote uploadFile 的网络层）。
/** 上传图片，返回可直接用于 <img> / markdown 的同源相对 URL。失败抛 Error(detail)。 */
export async function uploadDocImage(
  threadId: string,
  file: File,
): Promise<{ url: string }> {
  const token = /(?:^|;\s*)csrf_token=([^;]+)/.exec(document.cookie)?.[1] ?? "";
  const form = new FormData();
  form.append("file", file);
  const resp = await fetch(
    `/api/extensions/docmgr/threads/${encodeURIComponent(threadId)}/images`,
    {
      method: "POST",
      body: form,
      credentials: "include",
      headers: token ? { "X-CSRF-Token": token } : undefined,
    },
  );
  if (!resp.ok) {
    let detail = `图片上传失败 (${resp.status})`;
    try {
      const body: unknown = await resp.json();
      if (
        typeof body === "object" &&
        body !== null &&
        "detail" in body &&
        typeof (body as { detail: unknown }).detail === "string"
      )
        detail = (body as { detail: string }).detail;
    } catch {
      /* 非 JSON 响应，用默认文案 */
    }
    throw new Error(detail);
  }
  return (await resp.json()) as { url: string };
}
