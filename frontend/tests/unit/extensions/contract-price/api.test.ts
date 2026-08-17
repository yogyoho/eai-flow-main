import { describe, expect, rs, test } from "@rstest/core";

// EAI-CUSTOM: rs.mock is NOT fully hoisted under rstest — the module import
// must follow the mock or authFetch resolves to the unmocked export (same
// pattern as tests/unit/extensions/project/api.test.ts).
rs.mock("@/extensions/api/client", () => ({
  authFetch: rs.fn(),
}));

import { authFetch } from "@/extensions/api/client";
import { contractPriceApi, qs } from "@/extensions/contract-price/api";

function lastCall(): [string, RequestInit] {
  const calls = rs.mocked(authFetch).mock.calls;
  return calls[calls.length - 1] as unknown as [string, RequestInit];
}

describe("qs", () => {
  test("skips empty/null/undefined values", () => {
    expect(qs({ a: "x", b: "", c: undefined, d: null, e: 0 })).toBe("?a=x&e=0");
  });

  test("returns empty string for all-empty input", () => {
    expect(qs({ a: undefined, b: "" })).toBe("");
    expect(qs()).toBe("");
  });

  test("stringifies numbers and booleans", () => {
    expect(qs({ skip: 0, limit: 20, only_outliers: true })).toBe("?skip=0&limit=20&only_outliers=true");
  });
});


describe("contractPriceApi", () => {
  test("listDocuments builds the documents URL with params", async () => {
    rs.mocked(authFetch).mockResolvedValue({ items: [], total: 0, skip: 0, limit: 20 });
    await contractPriceApi.listDocuments({ keyword: "柜", skip: 0, limit: 20 });
    const [url] = lastCall();
    expect(url).toContain("/contract-price/documents");
    expect(url).toContain("keyword=%E6%9F%9C");
    expect(url).toContain("limit=20");
  });

  test("confirmCluster POSTs with the cluster id", async () => {
    rs.mocked(authFetch).mockResolvedValue({ status: "confirmed", version: 2 });
    await contractPriceApi.confirmCluster("c1", { expected_version: 1 });
    const [url, opts] = lastCall();
    expect(url).toBe("/contract-price/clusters/c1/confirm");
    expect(opts.method).toBe("POST");
  });

  test("runPipeline POSTs mode+trigger", async () => {
    rs.mocked(authFetch).mockResolvedValue({ run_id: "r1", status: "running", message: "ok" });
    await contractPriceApi.runPipeline("table", "manual");
    const [url, opts] = lastCall();
    expect(url).toBe("/contract-price/pipeline/run");
    expect(opts.method).toBe("POST");
    expect(opts.body).toEqual(JSON.stringify({ mode: "table", trigger: "manual" }));
  });

  test("deleteDocument uses DELETE method", async () => {
    rs.mocked(authFetch).mockResolvedValue(undefined);
    await contractPriceApi.deleteDocument("d1");
    const [url, opts] = lastCall();
    expect(url).toBe("/contract-price/documents/d1");
    expect(opts.method).toBe("DELETE");
  });
});
