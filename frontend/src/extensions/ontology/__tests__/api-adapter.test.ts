/**
 * Ontology 语义地图数据适配层契约测试 (EAI-CUSTOM, plan 2026-09-12 Task 2 Step 2.7).
 *
 * 本文件是 canonical 测试；`pnpm test`(rstest) 只发现 tests/unit/**，
 * 由 tests/unit/extensions/ontology/api-adapter.test.ts 镜像引入后运行。
 *
 * 走真实 authFetch + stub globalThis.fetch（复刻 bid-materials 的自包含 fetch 模式），
 * 这样能钉死含 /api/extensions 前缀的完整线上 URL 形态——若适配层误传全路径给
 * authFetch 会产生双前缀，此模式可直接暴露。node 环境无 document → CSRF 静默跳过。
 */
import { afterEach, describe, expect, test } from "@rstest/core";

import {
  fetchEdges,
  fetchNodes,
  fetchObjectTypes,
  fetchRegistryMeta,
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

describe("ontology-graph-api URL assembly", () => {
  test("fetchNodes without cursor hits /graph/nodes?limit=500 (no cursor param)", async () => {
    stubFetch(200, { nodes: [], next_cursor: null });
    await fetchNodes();
    const [url, init] = lastCall();
    expect(url).toBe("/api/extensions/ontology/graph/nodes?limit=500");
    expect(init.method).toBeUndefined(); // GET 免 CSRF：不设 method → fetch 默认 GET
    expect(init.credentials).toBe("include");
  });

  test("fetchNodes with cursor appends encoded cursor (opaque passthrough)", async () => {
    stubFetch(200, { nodes: [], next_cursor: null });
    // T1 游标 = base64(urlsafe_json)，尾部可能带 '=' —— 必须被 encodeURIComponent
    const cursor = "eyJ0eXBlX2lkeCI6Miwib2Zmc2V0Ijo1MH0=";
    await fetchNodes(cursor);
    const [url] = lastCall();
    expect(url).toBe(
      "/api/extensions/ontology/graph/nodes?limit=500&cursor=eyJ0eXBlX2lkeCI6Miwib2Zmc2V0Ijo1MH0%3D",
    );
  });

  test("fetchEdges without cursor hits /graph/edges?limit=1000", async () => {
    stubFetch(200, { edges: [], next_cursor: null });
    await fetchEdges();
    const [url] = lastCall();
    expect(url).toBe("/api/extensions/ontology/graph/edges?limit=1000");
  });

  test("fetchEdges passes cursor through verbatim (encoded)", async () => {
    stubFetch(200, { edges: [], next_cursor: null });
    await fetchEdges("eyJ0eXBlX2lkeCI6MX0=");
    const [url] = lastCall();
    expect(url).toBe(
      "/api/extensions/ontology/graph/edges?limit=1000&cursor=eyJ0eXBlX2lkeCI6MX0%3D",
    );
  });
});

describe("ontology-graph-api response normalization", () => {
  test("empty/missing page fields normalize to empty arrays + null cursor", async () => {
    stubFetch(200, {});
    const nodesPage = await fetchNodes();
    expect(nodesPage).toEqual({ nodes: [], next_cursor: null });

    const edgesPage = await fetchEdges();
    expect(edgesPage).toEqual({ edges: [], next_cursor: null });
  });

  test("payload passes through nodes/next_cursor untouched", async () => {
    const payload = {
      nodes: [
        {
          id: "bid:B-1",
          type: "bid",
          label: "横城煤矿项目",
          properties: { bidId: "B-1", won: true },
        },
      ],
      next_cursor: "eyJ0eXBlX2lkeCI6MX0=",
    };
    stubFetch(200, payload);
    const page = await fetchNodes();
    expect(page.nodes).toHaveLength(1);
    expect(page.nodes[0]?.id).toBe("bid:B-1");
    expect(page.next_cursor).toBe("eyJ0eXBlX2lkeCI6MX0=");
  });
});

describe("ontology-graph-api meta endpoints", () => {
  test("fetchRegistryMeta hits /registry", async () => {
    stubFetch(200, {
      registry_version: 3,
      fingerprint: "ab12cd34",
      object_type_count: 2,
      link_type_count: 1,
    });
    const meta = await fetchRegistryMeta();
    const [url] = lastCall();
    expect(url).toBe("/api/extensions/ontology/registry");
    expect(meta.fingerprint).toBe("ab12cd34");
  });

  test("fetchObjectTypes hits /object-types", async () => {
    stubFetch(200, {
      object_types: [
        {
          name: "bid",
          display_name: "投标记录",
          description: "",
          pk: "bidId",
          properties: ["bidId", "projectName"],
        },
      ],
      link_types: [
        { name: "bid_quote", source: "bid", target: "quote", enabled: true },
      ],
    });
    const schema = await fetchObjectTypes();
    const [url] = lastCall();
    expect(url).toBe("/api/extensions/ontology/object-types");
    expect(schema.object_types[0]?.pk).toBe("bidId");
    expect(schema.link_types[0]?.enabled).toBe(true);
  });
});
