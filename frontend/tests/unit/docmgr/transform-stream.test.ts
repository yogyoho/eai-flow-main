import { describe, expect, test } from "@rstest/core";

import { docmgrApi, ApiError } from "@/extensions/api";
import type { DocAITransformEvent } from "@/extensions/api";

function ndjsonResponse(lines: unknown[], status = 200): Response {
  // 原始字符串条目按字面输出（"" 即真·空行）；其余 JSON.stringify。
  const body = lines
    .map((l) =>
      typeof l === "string" ? l + "\n" : JSON.stringify(l) + "\n",
    )
    .join("");
  return new Response(body, {
    status,
    headers: { "Content-Type": "application/x-ndjson" },
  });
}

describe("aiTransformStream（NDJSON 逐行事件）", () => {
  test("逐行解析并回调；空行跳过", async () => {
    const events: DocAITransformEvent[] = [];
    const fetchMock = async () =>
      ndjsonResponse([
        { type: "section_start", index: 0, total: 2, title: "一" },
        "", // 真·空行：跳过
        {
          type: "ops",
          index: 0,
          ops: [{ op: "replace_section", anchor: "一", content: "x" }],
        },
        { type: "done", total: 2, failed: [], skipped: [] },
      ]);
    const orig = globalThis.fetch;
    globalThis.fetch = fetchMock as typeof fetch;
    try {
      await docmgrApi.aiTransformStream<DocAITransformEvent>(
        { thread_id: "t", rel_path: "r", operation: "polish", content: "c" },
        (e) => events.push(e),
      );
    } finally {
      globalThis.fetch = orig;
    }
    expect(events.map((e) => e.type)).toEqual([
      "section_start",
      "ops",
      "done",
    ]);
  });

  test("非 2xx 抛 ApiError（带状态码与响应体）", async () => {
    const orig = globalThis.fetch;
    globalThis.fetch = async () => new Response("boom", { status: 400 });
    try {
      await expect(
        docmgrApi.aiTransformStream(
          { thread_id: "t", rel_path: "r", operation: "polish", content: "c" },
          () => undefined,
        ),
      ).rejects.toMatchObject({ status: 400 });
    } finally {
      globalThis.fetch = orig;
    }
    expect(ApiError).toBeDefined();
  });
});
