"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import type { Editor } from "@tiptap/react";
import { Trash2, Copy, ChevronUp, ChevronDown, GripVertical } from "lucide-react";

import {
  deleteTopLevelBlockAt,
  duplicateTopLevelBlockAt,
  moveTopLevelBlockAt,
  moveTopLevelBlockByTarget,
} from "../utils/blockOperations";

interface DragHandleProps {
  editor: Editor | null;
  getPos: () => number | null;
  onDragStart: (event: React.DragEvent<HTMLDivElement>) => void;
  onDragEnd: () => void;
}

interface OperationMenuProps {
  editor: Editor;
  getPos: () => number | null;
  onClose: () => void;
}

function OperationMenu({ editor, getPos, onClose }: OperationMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose();
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [onClose]);

  const deleteBlock = useCallback(() => {
    const nodePos = getPos();
    if (nodePos === null) return;

    deleteTopLevelBlockAt(editor, nodePos);
    onClose();
  }, [editor, getPos, onClose]);

  const duplicateBlock = useCallback(() => {
    const nodePos = getPos();
    if (nodePos === null) return;

    duplicateTopLevelBlockAt(editor, nodePos);
    onClose();
  }, [editor, getPos, onClose]);

  const moveBlockUp = useCallback(() => {
    const nodePos = getPos();
    if (nodePos === null) return;

    moveTopLevelBlockAt(editor, nodePos, "up");
    onClose();
  }, [editor, getPos, onClose]);

  const moveBlockDown = useCallback(() => {
    const nodePos = getPos();
    if (nodePos === null) return;

    moveTopLevelBlockAt(editor, nodePos, "down");
    onClose();
  }, [editor, getPos, onClose]);

  return (
    <div ref={menuRef} className="notion-drag-handle-menu">
      <button className="notion-drag-handle-menu-item" onClick={deleteBlock} title="删除">
        <Trash2 className="w-3.5 h-3.5" />
        <span>删除</span>
      </button>
      <button className="notion-drag-handle-menu-item" onClick={duplicateBlock} title="复制">
        <Copy className="w-3.5 h-3.5" />
        <span>复制</span>
      </button>
      <div className="notion-drag-handle-menu-divider" />
      <button className="notion-drag-handle-menu-item" onClick={moveBlockUp} title="上移">
        <ChevronUp className="w-3.5 h-3.5" />
        <span>上移</span>
      </button>
      <button className="notion-drag-handle-menu-item" onClick={moveBlockDown} title="下移">
        <ChevronDown className="w-3.5 h-3.5" />
        <span>下移</span>
      </button>
    </div>
  );
}

function DragHandle({ editor, getPos, onDragStart, onDragEnd }: DragHandleProps) {
  const [showMenu, setShowMenu] = useState(false);

  if (!editor) return null;

  return (
    <div className="notion-drag-handle-wrapper">
      <div
        className="notion-drag-handle"
        onClick={() => setShowMenu((prev) => !prev)}
        onMouseDown={(e) => {
          if (e.detail === 2) e.preventDefault();
        }}
        draggable
        onDragStart={onDragStart}
        onDragEnd={onDragEnd}
      >
        <GripVertical className="w-4 h-4" />
      </div>
      {showMenu && (
        <OperationMenu editor={editor} getPos={getPos} onClose={() => setShowMenu(false)} />
      )}
    </div>
  );
}

interface EditorDragHandleProps {
  editor: Editor | null;
}

function getBlockFromTarget(target: EventTarget | null): HTMLElement | null {
  if (!(target instanceof HTMLElement)) return null;

  return (
    (target.closest("[data-block]") as HTMLElement | null) ??
    (target.closest(".ProseMirror > *") as HTMLElement | null)
  );
}

export default function EditorDragHandle({ editor }: EditorDragHandleProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const draggedPosRef = useRef<number | null>(null);
  const [activeHandle, setActiveHandle] = useState<{
    pos: number;
    top: number;
    left: number;
  } | null>(null);

  useEffect(() => {
    if (!editor) return;

    const editorDom = editor.view.dom as HTMLElement;

    const updateActiveHandle = (block: HTMLElement | null) => {
      if (!block) return;

      const domPos = editor.view.posAtDOM(block, 0);
      if (domPos === null || domPos === undefined) return;

      const rect = block.getBoundingClientRect();
      const editorRect = editorDom.getBoundingClientRect();
      setActiveHandle({
        pos: domPos,
        top: rect.top - editorRect.top + editorDom.scrollTop,
        left: -28,
      });
    };

    const handleMouseOver = (e: MouseEvent) => {
      updateActiveHandle(getBlockFromTarget(e.target));
    };

    const handleMouseOut = (e: MouseEvent) => {
      const relatedTarget = e.relatedTarget as HTMLElement | null;
      if (relatedTarget?.closest(".notion-drag-handle-wrapper")) return;
      setActiveHandle(null);
    };

    const handleDragOver = (e: DragEvent) => {
      if (draggedPosRef.current === null) return;

      const block = getBlockFromTarget(e.target);
      if (!block) return;

      e.preventDefault();
      updateActiveHandle(block);
    };

    const handleDrop = (e: DragEvent) => {
      if (draggedPosRef.current === null) return;

      const sourcePos = draggedPosRef.current;
      draggedPosRef.current = null;

      const block = getBlockFromTarget(e.target);
      if (!block) return;

      e.preventDefault();
      const targetPos = editor.view.posAtDOM(block, 0);
      if (targetPos === null || targetPos === undefined) return;

      moveTopLevelBlockByTarget(editor, sourcePos, targetPos);
      setActiveHandle(null);
    };

    editorDom.addEventListener("mouseover", handleMouseOver);
    editorDom.addEventListener("mouseout", handleMouseOut);
    editorDom.addEventListener("dragover", handleDragOver);
    editorDom.addEventListener("drop", handleDrop);

    return () => {
      editorDom.removeEventListener("mouseover", handleMouseOver);
      editorDom.removeEventListener("mouseout", handleMouseOut);
      editorDom.removeEventListener("dragover", handleDragOver);
      editorDom.removeEventListener("drop", handleDrop);
    };
  }, [editor]);

  const getPos = useCallback(() => activeHandle?.pos ?? null, [activeHandle]);

  return (
    <div ref={containerRef} className="notion-drag-handle-container">
      {activeHandle && (
        <div
          className="notion-drag-handle-anchor"
          style={{
            position: "absolute",
            top: activeHandle.top,
            left: activeHandle.left,
          }}
        >
          <DragHandle
            editor={editor}
            getPos={getPos}
            onDragStart={(event) => {
              const pos = getPos();
              if (pos === null) return;

              draggedPosRef.current = pos;
              event.dataTransfer.effectAllowed = "move";
              event.dataTransfer.setData("text/plain", String(pos));
            }}
            onDragEnd={() => {
              draggedPosRef.current = null;
            }}
          />
        </div>
      )}
    </div>
  );
}
