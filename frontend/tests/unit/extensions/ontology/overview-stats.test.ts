/**
 * 语义地图概览统计纯函数测试 (EAI-CUSTOM, plan semantic-map v2 Task 3 Step 3.2).
 *
 * 6 节点 4 边固定 mock：company×3 / contract×2 / goods×1；
 * 边 n1→n3, n1→n4, n2→n3, n3→n5（n6 孤点）。
 * 期望度数：n3=3, n1=2, n2/n4/n5=1, n6=0（孤点不进 Hub 榜）。
 */
import { describe, expect, test } from "@rstest/core";

import {
  communitySizes,
  degreeTop,
  typeDistribution,
} from "@/extensions/ontology/stats";

const NODES = [
  { id: "n1", type: "company", label: "alpha" },
  { id: "n2", type: "company", label: "beta" },
  { id: "n3", type: "contract", label: "hub-c" },
  { id: "n4", type: "contract", label: "delta" },
  { id: "n5", type: "goods", label: "echo" },
  { id: "n6", type: "company", label: "fox" },
];

const EDGES = [
  { source: "n1", target: "n3" },
  { source: "n1", target: "n4" },
  { source: "n2", target: "n3" },
  { source: "n3", target: "n5" },
];

describe("typeDistribution", () => {
  test("按 type 计数且降序排列", () => {
    expect(typeDistribution(NODES)).toEqual([
      { name: "company", count: 3 },
      { name: "contract", count: 2 },
      { name: "goods", count: 1 },
    ]);
  });

  test("空输入返回空数组", () => {
    expect(typeDistribution([])).toEqual([]);
  });
});

describe("degreeTop", () => {
  test("按度数降序，孤点不进榜", () => {
    const top = degreeTop(NODES, EDGES);
    expect(top[0]).toEqual({ label: "hub-c", degree: 3 });
    expect(top[1]).toEqual({ label: "alpha", degree: 2 });
    // n6 (fox) 度为 0，不进榜 → 全榜只有 5 人
    expect(top).toHaveLength(5);
    expect(top.some((entry) => entry.label === "fox")).toBe(false);
  });

  test("n 截断 Top N", () => {
    const top2 = degreeTop(NODES, EDGES, 2);
    expect(top2).toHaveLength(2);
    expect(top2.map((entry) => entry.label)).toEqual(["hub-c", "alpha"]);
    expect(degreeTop(NODES, EDGES, 3)[2]).toEqual({ label: "beta", degree: 1 });
  });

  test("空输入/无边图返回空数组", () => {
    expect(degreeTop([], [])).toEqual([]);
    expect(degreeTop(NODES, [])).toEqual([]);
  });
});

describe("communitySizes", () => {
  test("至少 1 个社区，labels 并集覆盖全部节点，规模降序", () => {
    const communities = communitySizes(NODES, EDGES);
    expect(communities.length).toBeGreaterThanOrEqual(1);
    const union = new Set(communities.flatMap((entry) => entry.labels));
    expect(union.size).toBe(NODES.length);
    for (const node of NODES) {
      expect(union.has(node.label)).toBe(true);
    }
    for (let i = 1; i < communities.length; i += 1) {
      expect(communities[i - 1]!.size).toBeGreaterThanOrEqual(
        communities[i]!.size,
      );
    }
  });

  test("空输入返回空数组（不抛）", () => {
    expect(communitySizes([], [])).toEqual([]);
  });
});
