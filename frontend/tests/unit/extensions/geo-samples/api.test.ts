import { describe, expect, rs, test } from "@rstest/core";

// EAI-CUSTOM: rs.mock is NOT fully hoisted under rstest — the module import
// must follow the mock or authFetch resolves to the unmocked export (same
// pattern as tests/unit/extensions/contract-price/api.test.ts).
rs.mock("@/extensions/api/client", () => ({
  authFetch: rs.fn(),
  authFormFetch: rs.fn(),
}));

import { authFetch, authFormFetch } from "@/extensions/api/client";
import { geoSamplesApi, qs } from "@/extensions/geo-samples/api";

function lastCall(): [string, RequestInit] {
  const calls = rs.mocked(authFetch).mock.calls;
  return calls[calls.length - 1] as unknown as [string, RequestInit];
}

function lastFormCall(): [string, FormData] {
  const calls = rs.mocked(authFormFetch).mock.calls;
  return calls[calls.length - 1] as unknown as [string, FormData];
}

describe("qs", () => {
  test("skips empty values", () => {
    expect(qs({ stage: "exploration", status: "", mineral: undefined })).toBe(
      "?stage=exploration",
    );
  });

  test("returns empty string for all-empty input", () => {
    expect(qs({ a: undefined, b: "" })).toBe("");
    expect(qs()).toBe("");
  });
});

describe("geoSamplesApi", () => {
  test("listDocuments builds URL with filters", async () => {
    rs.mocked(authFetch).mockResolvedValue({ items: [], skip: 0, limit: 50 });
    await geoSamplesApi.listDocuments({
      stage: "exploration",
      mineral: "gold",
      status: "redacted",
    });
    const [url] = lastCall();
    expect(url).toContain("/geo-samples/documents");
    expect(url).toContain("mineral=gold");
    expect(url).toContain("status=redacted");
  });

  test("review POSTs decision", async () => {
    rs.mocked(authFetch).mockResolvedValue({ id: "d1", status: "reviewed" });
    await geoSamplesApi.review("d1", { decision: "approve", note: null });
    const [url, opts] = lastCall();
    expect(url).toBe("/geo-samples/documents/d1/review");
    expect(opts.method).toBe("POST");
    expect(opts.body).toEqual(
      JSON.stringify({ decision: "approve", note: null }),
    );
  });

  test("uploadDocument posts FormData via authFormFetch", async () => {
    rs.mocked(authFormFetch).mockResolvedValue({ document: {}, run_id: "r1" });
    const fd = new FormData();
    fd.append("file", "dummy");
    fd.append("report_id", "r-1");
    await geoSamplesApi.uploadDocument(fd);
    const [url, body] = lastFormCall();
    expect(url).toBe("/geo-samples/documents/upload");
    expect(body).toBeInstanceOf(FormData);
  });

  test("parse POSTs and returns run_id", async () => {
    rs.mocked(authFetch).mockResolvedValue({ run_id: "run-1" });
    await geoSamplesApi.parse("d1");
    const [url, opts] = lastCall();
    expect(url).toBe("/geo-samples/documents/d1/parse");
    expect(opts.method).toBe("POST");
  });

  // suggest-id 端点为 POST ?title=Query(...)：漏 method 会走 GET 405；漏 encodeURIComponent
  // 会让 &/= 截断查询参数（P3-T7）。
  test("suggestId POSTs query-encoded title", async () => {
    rs.mocked(authFetch).mockResolvedValue({ report_id: "gsb-kc-cu-0001" });
    await geoSamplesApi.suggestId("某铜矿&阶段=勘探");
    const [url, opts] = lastCall();
    expect(url).toBe(
      `/geo-samples/documents/suggest-id?title=${encodeURIComponent("某铜矿&阶段=勘探")}`,
    );
    expect(opts.method).toBe("POST");
  });
});
