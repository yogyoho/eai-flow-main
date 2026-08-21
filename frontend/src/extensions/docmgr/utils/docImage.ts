// EAI-CUSTOM: 上传图片到个人文档（BlockNote uploadFile 的网络层）。
/** 上传图片，返回可直接用于 <img> / markdown 的同源相对 URL。失败抛 Error(detail)。 */
async function uploadImageTo(url: string, file: File): Promise<{ url: string }> {
  const token = /(?:^|;\s*)csrf_token=([^;]+)/.exec(document.cookie)?.[1] ?? "";
  const form = new FormData();
  form.append("file", file);
  const resp = await fetch(url, {
    method: "POST",
    body: form,
    credentials: "include",
    headers: token ? { "X-CSRF-Token": token } : undefined,
  });
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
  const body: unknown = await resp.json();
  if (
    typeof body === "object" &&
    body !== null &&
    "url" in body &&
    typeof (body as { url: unknown }).url === "string" &&
    (body as { url: string }).url
  )
    return { url: (body as { url: string }).url };
  throw new Error("图片上传响应异常");
}

/** 有线程文档：落盘线程 user-data/outputs/images/。 */
export function uploadDocImage(threadId: string, file: File): Promise<{ url: string }> {
  return uploadImageTo(`/api/extensions/docmgr/threads/${encodeURIComponent(threadId)}/images`, file);
}

/** 无线程文档（docmgr 直接新建）：落盘用户级 docmgr-images/ 目录。 */
export function uploadUserDocImage(file: File): Promise<{ url: string }> {
  return uploadImageTo("/api/extensions/docmgr/images", file);
}
