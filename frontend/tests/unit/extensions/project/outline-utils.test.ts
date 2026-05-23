import { expect, test, describe } from "vitest";

import type { ChapterTreeNode } from "@/extensions/project/types";

/**
 * Pure-function tests for the OutlineEditor tree operations.
 * These mirror the internal getAtPath/setAtPath/removeAtPath helpers
 * and test the tree manipulation logic independently of React.
 */

function getAtPath(nodes: ChapterTreeNode[], path: number[]): ChapterTreeNode | null {
  let current = nodes;
  let node: ChapterTreeNode | null = null;
  for (const idx of path) {
    if (idx >= current.length) return null;
    node = current[idx] ?? null;
    if (!node) return null;
    current = node.children;
  }
  return node;
}

function setAtPath(
  nodes: ChapterTreeNode[],
  path: number[],
  updater: (node: ChapterTreeNode) => ChapterTreeNode,
): ChapterTreeNode[] {
  if (path.length === 0) return nodes;
  const [head, ...rest] = path;
  return nodes.map((node, i) => {
    if (i !== head) return node;
    if (rest.length === 0) return updater(node);
    return { ...node, children: setAtPath(node.children, rest, updater) };
  });
}

function removeAtPath(nodes: ChapterTreeNode[], path: number[]): ChapterTreeNode[] {
  if (path.length === 0) return nodes;
  const [head, ...rest] = path;
  if (rest.length === 0) {
    return nodes.filter((_, i) => i !== head);
  }
  return nodes.map((node, i) => {
    if (i !== head) return node;
    return { ...node, children: removeAtPath(node.children, rest) };
  });
}

function makeNode(title: string, level: number = 1, children: ChapterTreeNode[] = []): ChapterTreeNode {
  return { title, level, sortOrder: 0, children };
}

// ── getAtPath ──

describe("getAtPath", () => {
  test("returns root node at index 0", () => {
    const nodes = [makeNode("A"), makeNode("B")];
    expect(getAtPath(nodes, [0])?.title).toBe("A");
    expect(getAtPath(nodes, [1])?.title).toBe("B");
  });

  test("returns nested child", () => {
    const child = makeNode("Child", 2);
    const root = makeNode("Root", 1, [child]);
    const nodes = [root];
    expect(getAtPath(nodes, [0, 0])?.title).toBe("Child");
  });

  test("returns deeply nested node", () => {
    const leaf = makeNode("Leaf", 3);
    const mid = makeNode("Mid", 2, [leaf]);
    const root = makeNode("Root", 1, [mid]);
    expect(getAtPath([root], [0, 0, 0])?.title).toBe("Leaf");
  });

  test("returns null for out-of-bounds", () => {
    const nodes = [makeNode("A")];
    expect(getAtPath(nodes, [5])).toBeNull();
  });

  test("returns null for empty path", () => {
    const nodes = [makeNode("A")];
    expect(getAtPath(nodes, [])).toBeNull();
  });

  test("returns null for out-of-bounds child path", () => {
    const root = makeNode("Root", 1, [makeNode("Child", 2)]);
    expect(getAtPath([root], [0, 5])).toBeNull();
  });
});

// ── setAtPath ──

describe("setAtPath", () => {
  test("updates title of root node", () => {
    const nodes = [makeNode("A"), makeNode("B")];
    const result = setAtPath(nodes, [0], (n) => ({ ...n, title: "Updated" }));
    expect(result[0].title).toBe("Updated");
    expect(result[1].title).toBe("B");
  });

  test("updates nested child", () => {
    const child = makeNode("Child", 2);
    const root = makeNode("Root", 1, [child]);
    const result = setAtPath([root], [0, 0], (n) => ({ ...n, title: "Updated Child" }));
    expect(result[0].children[0].title).toBe("Updated Child");
  });

  test("does not mutate original", () => {
    const nodes = [makeNode("A")];
    const result = setAtPath(nodes, [0], (n) => ({ ...n, title: "Changed" }));
    expect(nodes[0].title).toBe("A");
    expect(result[0].title).toBe("Changed");
  });

  test("returns unchanged for empty path", () => {
    const nodes = [makeNode("A")];
    expect(setAtPath(nodes, [], (n) => n)).toBe(nodes);
  });
});

// ── removeAtPath ──

describe("removeAtPath", () => {
  test("removes root node", () => {
    const nodes = [makeNode("A"), makeNode("B"), makeNode("C")];
    const result = removeAtPath(nodes, [1]);
    expect(result).toHaveLength(2);
    expect(result[0].title).toBe("A");
    expect(result[1].title).toBe("C");
  });

  test("removes nested child", () => {
    const root = makeNode("Root", 1, [makeNode("C1", 2), makeNode("C2", 2)]);
    const result = removeAtPath([root], [0, 0]);
    expect(result[0].children).toHaveLength(1);
    expect(result[0].children[0].title).toBe("C2");
  });

  test("does not mutate original", () => {
    const nodes = [makeNode("A"), makeNode("B")];
    removeAtPath(nodes, [0]);
    expect(nodes).toHaveLength(2);
  });

  test("returns unchanged for empty path", () => {
    const nodes = [makeNode("A")];
    expect(removeAtPath(nodes, [])).toBe(nodes);
  });

  test("handles removing only child", () => {
    const root = makeNode("Root", 1, [makeNode("Only", 2)]);
    const result = removeAtPath([root], [0, 0]);
    expect(result[0].children).toHaveLength(0);
  });
});

// ── tree manipulation workflows ──

describe("tree workflows", () => {
  test("add root node", () => {
    const nodes: ChapterTreeNode[] = [];
    const newNode = makeNode("New Chapter", 1);
    newNode.sortOrder = 0;
    const result = [...nodes, newNode];
    expect(result).toHaveLength(1);
    expect(result[0].title).toBe("New Chapter");
  });

  test("add child to existing node", () => {
    const root = makeNode("Root", 1);
    const nodes = [root];
    const newChild = makeNode("New Child", 2);
    const result = setAtPath(nodes, [0], (n) => ({
      ...n,
      children: [...n.children, newChild],
    }));
    expect(result[0].children).toHaveLength(1);
    expect(result[0].children[0].title).toBe("New Child");
  });

  test("rename and remove in sequence", () => {
    const nodes = [makeNode("A"), makeNode("B"), makeNode("C")];
    // Rename B
    const renamed = setAtPath(nodes, [1], (n) => ({ ...n, title: "B-Renamed" }));
    // Remove C
    const result = removeAtPath(renamed, [2]);
    expect(result).toHaveLength(2);
    expect(result[0].title).toBe("A");
    expect(result[1].title).toBe("B-Renamed");
  });
});
