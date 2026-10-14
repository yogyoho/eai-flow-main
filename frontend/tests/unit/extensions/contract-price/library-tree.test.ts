/**
 * EAI-CUSTOM cpa v3: 文件夹树构建/路径链纯函数单测。
 * 对应源: src/extensions/contract-price/components/library-tree.ts
 */
import { describe, expect, test } from "@rstest/core";

import {
  buildFolderTree,
  pathOf,
} from "@/extensions/contract-price/components/library-tree";

const FOLDERS = [
  { id: "b", parent_id: null, name: "2026 年合同" },
  { id: "b1", parent_id: "b", name: "矿建工程" },
  { id: "a", parent_id: null, name: "2025 年合同" },
  { id: "b2", parent_id: "b", name: "设备采购" },
];

describe("buildFolderTree", () => {
  test("根级按名称排序、子级挂到父节点", () => {
    const tree = buildFolderTree(FOLDERS);
    expect(tree.map((n) => n.name)).toEqual(["2025 年合同", "2026 年合同"]);
    const b = tree[1]!;
    expect(b.children.map((n) => n.id)).toEqual(["b1", "b2"]);
  });

  test("空输入返回空树", () => {
    expect(buildFolderTree([])).toEqual([]);
  });
});

describe("pathOf", () => {
  test("含虚拟根的路径链", () => {
    expect(pathOf(FOLDERS, "b2")).toEqual([
      { id: "root", name: "文件库" },
      { id: "b", name: "2026 年合同" },
      { id: "b2", name: "设备采购" },
    ]);
  });

  test("root 直接返回单节", () => {
    expect(pathOf(FOLDERS, "root")).toEqual([{ id: "root", name: "文件库" }]);
  });

  test("深度帽截断: 70 层 parent 链不挂死, 丢弃 chain 返回 [虚拟根] 单节", () => {
    const chain = Array.from({ length: 70 }, (_, i) => ({
      id: `f${i}`,
      parent_id: i === 0 ? null : `f${i - 1}`,
      name: `层${i}`,
    }));
    expect(pathOf(chain, "f69")).toEqual([{ id: "root", name: "文件库" }]);
  });

  test("成环 parent 链同样截断为 [虚拟根] 单节", () => {
    const cycle = [
      { id: "x", parent_id: "y", name: "X" },
      { id: "y", parent_id: "x", name: "Y" },
    ];
    expect(pathOf(cycle, "x")).toEqual([{ id: "root", name: "文件库" }]);
  });
});
