import { describe, expect, it, vi, beforeEach } from "vitest";

import { contractPriceApi, qs } from "@/extensions/contract-price/api";

// Mock authFetch so tests assert URL + method without hitting the network.
vi.mock("@/extensions/api/client", () => ({
  authFetch: vi.fn(),
}));

import { authFetch } from "@/extensions/api/client";

describe("qs", () => {
  it("skips empty/null/undefined values", () => {
    expect(qs({ a: "x", b: "", c: undefined, d: null, e: 0 })).toBe("?a=x&e=0");
  });

  it("returns empty string for all-empty input", () => {
    expect(qs({ a: undefined, b: "" })).toBe("");
  });

  it("stringifies numbers and booleans", () => {
    expect(qs({ skip: 0, limit: 20, only_outliers: true })).toBe("?skip=0&limit=20&only_outliers=true");
  });
});

describe("contractPriceApi", () => {
  beforeEach(() => vi.clearAllMocks());

  it("listDocuments builds the documents URL with params", async () => {
    vi.mocked(authFetch).mockResolvedValue({ items: [], total: 0, skip: 0, limit: 20 });
    await contractPriceApi.listDocuments({ keyword: "柜", skip: 0, limit: 20 });
    const [url] = vi.mocked(authFetch).mock.calls[0];
    expect(url).toContain("/contract-price/documents");
    expect(url).toContain("keyword=%E6%9F%9C");
    expect(url).toContain("limit=20");
  });

  it("confirmCluster POSTs with the cluster id", async () => {
    vi.mocked(authFetch).mockResolvedValue({ status: "confirmed", version: 2 });
    await contractPriceApi.confirmCluster("c1", { expected_version: 1 });
    const [url, opts] = vi.mocked(authFetch).mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/contract-price/clusters/c1/confirm");
    expect(opts.method).toBe("POST");
  });

  it("runPipeline POSTs mode+trigger", async () => {
    vi.mocked(authFetch).mockResolvedValue({ run_id: "r1", status: "running", message: "ok" });
    await contractPriceApi.runPipeline("table", "manual");
    const [url, opts] = vi.mocked(authFetch).mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/contract-price/pipeline/run");
    expect(opts.method).toBe("POST");
    expect(opts.body).toEqual(JSON.stringify({ mode: "table", trigger: "manual" }));
  });

  it("deleteDocument uses DELETE method", async () => {
    vi.mocked(authFetch).mockResolvedValue(undefined);
    await contractPriceApi.deleteDocument("d1");
    const [url, opts] = vi.mocked(authFetch).mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/contract-price/documents/d1");
    expect(opts.method).toBe("DELETE");
  });
});
