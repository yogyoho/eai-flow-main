import type { Editor } from "@tiptap/react";
import { Fragment, type Node as ProseMirrorNode } from "@tiptap/pm/model";
import { TextSelection } from "@tiptap/pm/state";

function getTopLevelBlocks(doc: ProseMirrorNode): ProseMirrorNode[] {
  const blocks: ProseMirrorNode[] = [];
  doc.forEach((node) => {
    blocks.push(node);
  });
  return blocks;
}

export function getTopLevelBlockIndex(doc: ProseMirrorNode, pos: number): number | null {
  if (doc.childCount === 0) return null;

  const $pos = doc.resolve(Math.max(0, Math.min(pos, doc.content.size)));
  const index = $pos.index(0);
  return index >= 0 && index < doc.childCount ? index : null;
}

export function removeTopLevelBlock(
  blocks: ProseMirrorNode[],
  index: number
): ProseMirrorNode[] | null {
  if (index < 0 || index >= blocks.length) return null;
  return blocks.filter((_, currentIndex) => currentIndex !== index);
}

export function duplicateTopLevelBlock(
  blocks: ProseMirrorNode[],
  index: number
): ProseMirrorNode[] | null {
  const block = blocks[index];
  if (!block) return null;

  return [
    ...blocks.slice(0, index + 1),
    block,
    ...blocks.slice(index + 1),
  ];
}

export function moveTopLevelBlock(
  blocks: ProseMirrorNode[],
  index: number,
  direction: "up" | "down"
): ProseMirrorNode[] | null {
  const targetIndex = direction === "up" ? index - 1 : index + 1;
  return moveTopLevelBlockToIndex(blocks, index, targetIndex);
}

export function moveTopLevelBlockToIndex(
  blocks: ProseMirrorNode[],
  fromIndex: number,
  toIndex: number
): ProseMirrorNode[] | null {
  if (
    fromIndex < 0 ||
    fromIndex >= blocks.length ||
    toIndex < 0 ||
    toIndex >= blocks.length ||
    fromIndex === toIndex
  ) {
    return null;
  }

  const nextBlocks = [...blocks];
  const [movedBlock] = nextBlocks.splice(fromIndex, 1);
  if (!movedBlock) return null;
  nextBlocks.splice(toIndex, 0, movedBlock);
  return nextBlocks;
}

function getBlockSelectionPos(blocks: ProseMirrorNode[], index: number): number {
  const offset = blocks
    .slice(0, index)
    .reduce((total, block) => total + block.nodeSize, 0);
  const docSize = blocks.reduce((total, block) => total + block.nodeSize, 0);

  return Math.max(1, Math.min(offset + 1, docSize));
}

function replaceTopLevelBlocks(
  editor: Editor,
  blocks: ProseMirrorNode[],
  selectionIndex: number
): boolean {
  const { state } = editor;
  const tr = state.tr.replaceWith(0, state.doc.content.size, Fragment.fromArray(blocks));
  const nextSelectionIndex = Math.max(0, Math.min(selectionIndex, blocks.length - 1));
  const selectionPos = getBlockSelectionPos(blocks, nextSelectionIndex);

  tr.setSelection(TextSelection.near(tr.doc.resolve(selectionPos)));
  editor.view.dispatch(tr.scrollIntoView());
  editor.commands.focus();
  return true;
}

export function deleteTopLevelBlockAt(editor: Editor, pos: number): boolean {
  const { state } = editor;
  const index = getTopLevelBlockIndex(state.doc, pos);
  if (index === null) return false;

  const nextBlocks = removeTopLevelBlock(getTopLevelBlocks(state.doc), index);
  if (!nextBlocks || nextBlocks.length === 0) return false;

  return replaceTopLevelBlocks(editor, nextBlocks, Math.max(0, index - 1));
}

export function duplicateTopLevelBlockAt(editor: Editor, pos: number): boolean {
  const { state } = editor;
  const index = getTopLevelBlockIndex(state.doc, pos);
  if (index === null) return false;

  const nextBlocks = duplicateTopLevelBlock(getTopLevelBlocks(state.doc), index);
  if (!nextBlocks) return false;

  return replaceTopLevelBlocks(editor, nextBlocks, index + 1);
}

export function moveTopLevelBlockAt(
  editor: Editor,
  pos: number,
  direction: "up" | "down"
): boolean {
  const { state } = editor;
  const index = getTopLevelBlockIndex(state.doc, pos);
  if (index === null) return false;

  const nextBlocks = moveTopLevelBlock(getTopLevelBlocks(state.doc), index, direction);
  if (!nextBlocks) return false;

  return replaceTopLevelBlocks(editor, nextBlocks, direction === "up" ? index - 1 : index + 1);
}

export function moveTopLevelBlockByTarget(
  editor: Editor,
  sourcePos: number,
  targetPos: number
): boolean {
  const { state } = editor;
  const blocks = getTopLevelBlocks(state.doc);
  const fromIndex = getTopLevelBlockIndex(state.doc, sourcePos);
  const toIndex = getTopLevelBlockIndex(state.doc, targetPos);
  if (fromIndex === null || toIndex === null) return false;

  const nextBlocks = moveTopLevelBlockToIndex(blocks, fromIndex, toIndex);
  if (!nextBlocks) return false;

  return replaceTopLevelBlocks(editor, nextBlocks, toIndex);
}
