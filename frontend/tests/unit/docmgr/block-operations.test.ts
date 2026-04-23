import { Schema } from "@tiptap/pm/model";
import { expect, test } from "vitest";

import {
  duplicateTopLevelBlock,
  getTopLevelBlockIndex,
  moveTopLevelBlock,
  moveTopLevelBlockToIndex,
  removeTopLevelBlock,
} from "@/extensions/docmgr/utils/blockOperations";

const schema = new Schema({
  nodes: {
    doc: { content: "block+" },
    paragraph: {
      content: "text*",
      group: "block",
      toDOM: () => ["p", 0],
    },
    text: { group: "inline" },
  },
});

function createDoc(labels: string[]) {
  return schema.node(
    "doc",
    null,
    labels.map((label) => schema.node("paragraph", null, label ? [schema.text(label)] : []))
  );
}

function getBlocks(labels: string[]) {
  return createDoc(labels).content.content.slice();
}

test("getTopLevelBlockIndex resolves a position inside a top-level block", () => {
  const doc = createDoc(["A", "B", "C"]);
  expect(getTopLevelBlockIndex(doc, 1)).toBe(0);
  expect(getTopLevelBlockIndex(doc, 4)).toBe(1);
});

test("duplicateTopLevelBlock inserts a copy after the current block", () => {
  const next = duplicateTopLevelBlock(getBlocks(["A", "B", "C"]), 1);
  expect(next?.map((node) => node.textContent)).toEqual(["A", "B", "B", "C"]);
});

test("removeTopLevelBlock removes the targeted block", () => {
  const next = removeTopLevelBlock(getBlocks(["A", "B", "C"]), 1);
  expect(next?.map((node) => node.textContent)).toEqual(["A", "C"]);
});

test("moveTopLevelBlock swaps blocks upward and downward", () => {
  const blocks = getBlocks(["A", "B", "C"]);
  expect(moveTopLevelBlock(blocks, 1, "up")?.map((node) => node.textContent)).toEqual(["B", "A", "C"]);
  expect(moveTopLevelBlock(blocks, 1, "down")?.map((node) => node.textContent)).toEqual(["A", "C", "B"]);
});

test("moveTopLevelBlockToIndex reorders by explicit target index", () => {
  const next = moveTopLevelBlockToIndex(getBlocks(["A", "B", "C"]), 0, 2);
  expect(next?.map((node) => node.textContent)).toEqual(["B", "C", "A"]);
});
