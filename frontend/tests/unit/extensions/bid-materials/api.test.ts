import { afterEach, describe, expect, test } from "@rstest/core";

import {
  bidMaterialsApi,
  QUAL_TYPE_PRESETS,
  SAMPLE_SCENARIOS,
} from "@/extensions/bid-materials/bid-materials-api";

// EAI-CUSTOM: bid-materials api 层契约测试——自包含 fetch 模式（复刻 eia-samples），
// 直接 stub globalThis.fetch（geo-samples 的 authFetch mock 模式不适用）。
// 断言对齐 backend/app/extensions/bid_materials/routers.py 实读契约（Plan 4 Task 1 核验）：
// rollback 体键 to_version；列表过滤仅后端实有参数（samples 搜索键名 q）；文件下发仅当前版。
// csrf cookie 在 node 环境缺失（document undefined）→ withCsrf 静默跳过，写方法断言只查
// method/body/URL；CSRF 头存在性由 withCsrf ≤10 行的直观性兜底（dom 语义，不在此断言）。
const fetchMock: { calls: Array<[string, RequestInit]> } = { calls: [] };

const originalFetch = globalThis.fetch;

function stubFetch(status = 200, body: unknown = {}) {
  fetchMock.calls = [];
  globalThis.fetch = (async (input: string | URL, init: RequestInit = {}) => {
    fetchMock.calls.push([String(input), init]);
    return new Response(JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    });
  }) as typeof fetch;
}

afterEach(() => {
  globalThis.fetch = originalFetch;
});

function lastCall(): [string, RequestInit] {
  const call = fetchMock.calls[fetchMock.calls.length - 1];
  if (!call) throw new Error("no fetch call recorded");
  return call;
}

describe("bidMaterialsApi.qualifications", () => {
  test("list builds query with backend-supported filters", async () => {
    stubFetch(200, []);
    await bidMaterialsApi.qualifications.list({
      qual_type: "CMMI",
      include_disabled: true,
      limit: 50,
    });
    const [url] = lastCall();
    expect(url.startsWith("/api/extensions/bid-materials/qualifications?")).toBe(true);
    expect(url).toContain("qual_type=CMMI");
    expect(url).toContain("include_disabled=true");
    expect(url).toContain("limit=50");
  });

  test("expiring hits dedicated endpoint with days", async () => {
    stubFetch(200, []);
    await bidMaterialsApi.qualifications.expiring(30);
    const [url] = lastCall();
    expect(url).toBe("/api/extensions/bid-materials/qualifications/expiring?days=30");
  });

  test("create POSTs json body with csrf attempt", async () => {
    stubFetch(201, { id: "q1" });
    await bidMaterialsApi.qualifications.create({ qual_type: "ISO9001", cert_no: "00123" });
    const [url, init] = lastCall();
    expect(url).toBe("/api/extensions/bid-materials/qualifications");
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ qual_type: "ISO9001", cert_no: "00123" }));
  });

  test("uploadVersion posts FormData(file+note) without json content-type", async () => {
    stubFetch(201, { created: true, version: 2, sha256: "ab" });
    const file = new File([new Uint8Array([1, 2, 3])], "cert.png", { type: "image/png" });
    await bidMaterialsApi.qualifications.uploadVersion("q1", file, "年审换证");
    const [url, init] = lastCall();
    expect(url).toBe("/api/extensions/bid-materials/qualifications/q1/versions");
    expect(init.method).toBe("POST");
    const form = init.body as FormData;
    expect(form).toBeInstanceOf(FormData);
    expect((form.get("file") as File).name).toBe("cert.png");
    expect(form.get("note")).toBe("年审换证");
    const headers = (init.headers ?? {}) as Record<string, string>;
    expect(headers["Content-Type"]).toBeUndefined();
  });

  test("rollback POSTs to_version body key", async () => {
    stubFetch(200, { id: "q1", current_version: 1 });
    await bidMaterialsApi.qualifications.rollback("q1", 1);
    const [url, init] = lastCall();
    expect(url).toBe("/api/extensions/bid-materials/qualifications/q1/rollback");
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ to_version: 1 }));
  });

  test("fileUrl is a plain GET link (cookie auth, no fetch, current version only)", () => {
    stubFetch();
    expect(bidMaterialsApi.qualifications.fileUrl("q1")).toBe(
      "/api/extensions/bid-materials/qualifications/q1/file",
    );
    expect(fetchMock.calls.length).toBe(0);
  });
});

describe("bidMaterialsApi.samples", () => {
  test("list builds query with backend-supported filters", async () => {
    stubFetch(200, []);
    await bidMaterialsApi.samples.list({
      industry: "IT",
      project_category: "software",
      q: "tender",
    });
    const [url] = lastCall();
    expect(url.startsWith("/api/extensions/bid-materials/samples?")).toBe(true);
    expect(url).toContain("industry=IT");
    expect(url).toContain("project_category=software");
    expect(url).toContain("q=tender");
  });

  test("importBulk posts items envelope to /samples/bulk", async () => {
    stubFetch(201, { created: 1, updated: 0, total: 1 });
    const item = {
      title: "t",
      source_path: "p",
      file_hash: "h".repeat(64),
      industry: "i",
      project_category: "c",
      scenario: "bid_sample",
      status: "indexed",
    };
    await bidMaterialsApi.samples.importBulk([item]);
    const [url, init] = lastCall();
    expect(url).toBe("/api/extensions/bid-materials/samples/bulk");
    expect(init.body).toBe(JSON.stringify({ items: [item] }));
  });

  test("disable uses DELETE", async () => {
    stubFetch(200, { message: "样例已停用" });
    await bidMaterialsApi.samples.disable("s1");
    const [url, init] = lastCall();
    expect(url).toBe("/api/extensions/bid-materials/samples/s1");
    expect(init.method).toBe("DELETE");
  });
});

describe("error mapping", () => {
  test("non-json error surfaces response text", async () => {
    globalThis.fetch = (async () => new Response("boom", { status: 500 })) as typeof fetch;
    await expect(bidMaterialsApi.samples.disable("s1")).rejects.toThrow("boom");
  });

  test("fastapi detail string is surfaced", async () => {
    stubFetch(400, { detail: "证号已存在" });
    await expect(
      bidMaterialsApi.qualifications.create({ qual_type: "ISO9001", cert_no: "y" }),
    ).rejects.toThrow("证号已存在");
  });
});

describe("enums", () => {
  test("scenario presets center on bid_sample", () => {
    expect(SAMPLE_SCENARIOS.some((s) => s.value === "bid_sample")).toBe(true);
  });

  test("qual type presets mirror backend QualType literal", () => {
    expect(QUAL_TYPE_PRESETS.length).toBeGreaterThan(3);
    expect(QUAL_TYPE_PRESETS.every((t) => t.value && t.label)).toBe(true);
    expect(QUAL_TYPE_PRESETS.map((t) => t.value)).toEqual([
      "营业执照",
      "CMMI",
      "ISO9001",
      "ISO27001",
      "业绩证明",
      "软件著作权",
      "高新技术企业",
      "其他",
    ]);
  });
});
