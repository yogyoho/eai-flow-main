/**
 * doc-graph 实体消解 REST 适配层契约测试 (EAI-CUSTOM, plan semantic-map v2 Task 4 Step 4.4).
 *
 * 本文件是 canonical 测试；`pnpm test`(rstest) 只发现 tests/unit/**，
 * 由 tests/unit/extensions/ontology/resolution-api.test.ts 镜像引入后运行。
 *
 * 走真实 authFetch + stub globalThis.fetch（复刻同目录 api-adapter.test.ts 模式）：
 * 钉死含 /api/extensions 前缀的完整线上 URL（extension-relative 路径误写全路径会
 * 产生双前缀，此模式直接暴露）、POST 请求体形状、错误语义透传。
 * node 环境无 document → CSRF 头静默跳过（浏览器端由 client.ts 自动注入）。
 */
import { afterEach, describe, expect, test } from "@rstest/core";

import {
  fetchPending,
  mergeEntities,
  PENDING_REVIEW_LIMIT,
  unmergeEntities,
} from "../api/ontology-graph-api";

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

/** RequestInit.body 只会由本适配层传入 string（JSON.stringify 产物），钉死形态用。 */
function bodyOf(init: RequestInit): string {
  return init.body as string;
}

describe("doc-graph resolution API wire contract", () => {
  test("fetchPending hits /doc-graph/resolution/pending?limit=200 (etype appended only when given)", async () => {
    stubFetch(200, { entities: [], count: 0 });
    await fetchPending();
    let [url] = lastCall();
    expect(url).toBe(
      `/api/extensions/doc-graph/resolution/pending?limit=${PENDING_REVIEW_LIMIT}`,
    );
    expect(lastCall()[1].method).toBeUndefined(); // GET 免 CSRF：不设 method → fetch 默认 GET
    expect(lastCall()[1].credentials).toBe("include");

    await fetchPending("project");
    [url] = lastCall();
    expect(url).toBe(
      `/api/extensions/doc-graph/resolution/pending?limit=${PENDING_REVIEW_LIMIT}&etype=project`,
    );
  });

  test("mergeEntities POSTs manual body {candidate_id, canonical_id, method, confidence} to /resolution/merge", async () => {
    stubFetch(200, {
      merge_id: "m-1",
      candidate_id: "c-1",
      canonical_id: "k-1",
    });
    const result = await mergeEntities("c-1", "k-1", 0.98);
    const [url, init] = lastCall();
    expect(url).toBe("/api/extensions/doc-graph/resolution/merge");
    expect(init.method).toBe("POST"); // 写操作：client.ts 在浏览器端自动注 X-CSRF-Token
    expect(JSON.parse(bodyOf(init))).toEqual({
      candidate_id: "c-1",
      canonical_id: "k-1",
      method: "manual",
      confidence: 0.98,
    });
    expect(result).toEqual({
      merge_id: "m-1",
      candidate_id: "c-1",
      canonical_id: "k-1",
    });

    // confidence 缺省 → 1.0（后端 MergeBody 默认同值）
    await mergeEntities("c-1", "k-1");
    expect(JSON.parse(bodyOf(lastCall()[1])).confidence).toBe(1.0);
  });

  test("404 with detail string propagates message + status through mergeEntities (auto-refetch contract)", async () => {
    stubFetch(404, { detail: "canonical xxx 不存在" });
    const error = (await mergeEntities("c-1", "k-1").catch(
      (caught: unknown) => caught,
    )) as Error & { status?: number };
    expect(error).toBeInstanceOf(Error);
    expect(error.status).toBe(404);
    expect(error.message).toBe("canonical xxx 不存在");
  });

  test("unmergeEntities POSTs {merge_id} to /resolution/unmerge and returns restored id", async () => {
    stubFetch(200, { restored_candidate_id: "c-1" });
    const result = await unmergeEntities("m-1");
    const [url, init] = lastCall();
    expect(url).toBe("/api/extensions/doc-graph/resolution/unmerge");
    expect(init.method).toBe("POST");
    expect(JSON.parse(bodyOf(init))).toEqual({ merge_id: "m-1" });
    expect(result.restored_candidate_id).toBe("c-1");
  });
});
