"use client";

import type { Editor } from "@tiptap/react";
import { Trash2, Copy, ChevronUp, ChevronDown, GripVertical } from "lucide-react";
import React, { useCallback, useEffect, useRef, useState } from "react";

import {
  deleteTopLevelBlockAt,
  duplicateTopLevelBlockAt,
  getTopLevelBlockIndex,
  moveTopLevelBlockAt,
  moveTopLevelBlockToPosition,
} from "../utils/blockOperations";

interface DragHandleProps {
  editor: Editor | null;
  getPos: () => number | null;
  onDragStart: (e: React.MouseEvent) => void;
  onHideCancel: () => void;
  didDragRef: React.RefObject<boolean>;
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

function DragHandle({ editor, getPos, onDragStart, onHideCancel, didDragRef }: DragHandleProps) {
  const [showMenu, setShowMenu] = useState(false);

  if (!editor) return null;

  return (
    <div className="notion-drag-handle-wrapper" onMouseEnter={onHideCancel}>
      <div
        className="notion-drag-handle notion-drag-handle--visible"
        onClick={() => {
          if (didDragRef.current) {
            didDragRef.current = false;
            return;
          }
          setShowMenu((prev) => !prev);
        }}
        onMouseDown={(e) => {
          if (e.detail === 2) e.preventDefault();
          onDragStart(e);
        }}
      >
        <GripVertical className="w-4 h-4" />
      </div>
      {showMenu && (
        <OperationMenu editor={editor} getPos={getPos} onClose={() => setShowMenu(false)} />
      )}
    </div>
  );
}

interface DropIndicatorState {
  top: number;
  targetIndex: number;
  placement: "before" | "after";
}

interface EditorDragHandleProps {
  editor: Editor | null;
  scrollContainerRef?: React.RefObject<HTMLDivElement | null>;
}

function getBlockFromTarget(target: EventTarget | null): HTMLElement | null {
  if (!(target instanceof HTMLElement)) return null;

  // Find the direct child of .ProseMirror (top-level block)
  const prosemirror = target.closest(".ProseMirror");
  if (!prosemirror) return null;

  // Walk up from target to find the direct child of .ProseMirror
  let el: HTMLElement | null = target;
  while (el && el.parentElement !== prosemirror) {
    el = el.parentElement;
  }
  return el;
}

function getBlockFromPoint(x: number, y: number): HTMLElement | null {
  const els = document.elementsFromPoint(x, y);
  for (const el of els) {
    if (!(el instanceof HTMLElement)) continue;
    const block = getBlockFromTarget(el);
    if (block) return block;
  }
  return null;
}

const SCROLL_ZONE = 60;
const SCROLL_SPEED = 10;

export default function EditorDragHandle({ editor, scrollContainerRef }: EditorDragHandleProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const hideTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const [activeHandle, setActiveHandle] = useState<{
    pos: number;
    top: number;
    left: number;
  } | null>(null);

  // Drag state
  const [isDragging, setIsDragging] = useState(false);
  const dragSourcePosRef = useRef<number | null>(null);
  const [dropIndicator, setDropIndicator] = useState<DropIndicatorState | null>(null);
  const dropIndicatorRef = useRef<DropIndicatorState | null>(null);
  const mouseRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const didDragRef = useRef(false);

  // Keep ref in sync with state for use in mouseup handler
  useEffect(() => {
    dropIndicatorRef.current = dropIndicator;
  }, [dropIndicator]);

  // Drag listeners ref so we can clean up
  const dragListenersRef = useRef<{
    mousemove: (e: MouseEvent) => void;
    mouseup: () => void;
    keydown: (e: KeyboardEvent) => void;
  } | null>(null);

  // Dim source block during drag
  useEffect(() => {
    if (!editor) return;
    const editorDom = editor.view.dom;

    editorDom.querySelectorAll(".notion-drag-source").forEach((el) => {
      el.classList.remove("notion-drag-source");
    });

    if (isDragging && dragSourcePosRef.current !== null) {
      try {
        const dom = editor.view.nodeDOM(dragSourcePosRef.current);
        if (dom instanceof HTMLElement) {
          dom.classList.add("notion-drag-source");
        }
      } catch {
        // pos may be stale
      }
    }
  }, [isDragging, editor]);

  // Handle mouse hover for showing/hiding grip icon
  useEffect(() => {
    if (!editor) return;

    const editorDom = editor.view.dom;

    const updateActiveHandle = (block: HTMLElement | null) => {
      if (!block) return;

      const domPos = editor.view.posAtDOM(block, 0);
      if (domPos === null || domPos === undefined) return;

      const containerEl = containerRef.current;
      if (!containerEl) return;

      const rect = block.getBoundingClientRect();
      const containerRect = containerEl.getBoundingClientRect();
      setActiveHandle({
        pos: domPos,
        top: rect.top - containerRect.top,
        left: 4,
      });
    };

    const handleMouseOver = (e: MouseEvent) => {
      if (isDragging) return;
      clearTimeout(hideTimerRef.current);
      updateActiveHandle(getBlockFromTarget(e.target));
    };

    const handleMouseOut = (e: MouseEvent) => {
      if (isDragging) return;
      const relatedTarget = e.relatedTarget as HTMLElement | null;
      if (relatedTarget?.closest(".notion-drag-handle-wrapper") || relatedTarget?.closest(".notion-drag-handle-menu")) return;
      hideTimerRef.current = setTimeout(() => setActiveHandle(null), 300);
    };

    editorDom.addEventListener("mouseover", handleMouseOver);
    editorDom.addEventListener("mouseout", handleMouseOut);

    return () => {
      editorDom.removeEventListener("mouseover", handleMouseOver);
      editorDom.removeEventListener("mouseout", handleMouseOut);
      clearTimeout(hideTimerRef.current);
    };
  }, [editor, isDragging]);

  const getPos = useCallback(() => activeHandle?.pos ?? null, [activeHandle]);

  const cancelHide = useCallback(() => {
    clearTimeout(hideTimerRef.current);
  }, []);

  const cancelDrag = useCallback(() => {
    setIsDragging(false);
    dragSourcePosRef.current = null;
    setDropIndicator(null);
    document.body.style.cursor = "";
    document.body.style.userSelect = "";

    if (dragListenersRef.current) {
      document.removeEventListener("mousemove", dragListenersRef.current.mousemove);
      document.removeEventListener("mouseup", dragListenersRef.current.mouseup);
      document.removeEventListener("keydown", dragListenersRef.current.keydown);
      dragListenersRef.current = null;
    }
  }, []);

  const handleDragStart = useCallback(
    (e: React.MouseEvent) => {
      const pos = getPos();
      if (pos === null) return;

      dragSourcePosRef.current = pos;
      didDragRef.current = false;

      let hasDragged = false;

      const handleMouseMove = (me: MouseEvent) => {
        mouseRef.current = { x: me.clientX, y: me.clientY };

        if (!hasDragged) {
          hasDragged = true;
          didDragRef.current = true;
          setIsDragging(true);
          setDropIndicator(null);
          document.body.style.cursor = "grabbing";
          document.body.style.userSelect = "none";
        }

        // Auto-scroll near edges
        const scrollEl = scrollContainerRef?.current;
        if (scrollEl) {
          const scrollRect = scrollEl.getBoundingClientRect();
          if (me.clientY < scrollRect.top + SCROLL_ZONE) {
            scrollEl.scrollTop -= SCROLL_SPEED;
          } else if (me.clientY > scrollRect.bottom - SCROLL_ZONE) {
            scrollEl.scrollTop += SCROLL_SPEED;
          }
        }

        // Find block under cursor
        const block = getBlockFromPoint(me.clientX, me.clientY);
        if (!block) {
          setDropIndicator(null);
          return;
        }

        const blockRect = block.getBoundingClientRect();
        const midY = blockRect.top + blockRect.height / 2;
        const placement = me.clientY < midY ? "before" : "after";

        // Get block index
        const blockPos = editor?.view.posAtDOM(block, 0);
        if (blockPos === null || blockPos === undefined || !editor) {
          setDropIndicator(null);
          return;
        }
        const blockIndex = getTopLevelBlockIndex(editor.state.doc, blockPos);
        if (blockIndex === null) {
          setDropIndicator(null);
          return;
        }

        // Compute indicator top position
        const containerEl = containerRef.current;
        if (!containerEl) return;
        const containerRect = containerEl.getBoundingClientRect();
        const indicatorTop =
          placement === "before"
            ? blockRect.top - containerRect.top
            : blockRect.bottom - containerRect.top;

        setDropIndicator({
          top: indicatorTop,
          targetIndex: blockIndex,
          placement,
        });
      };

      const handleMouseUp = () => {
        if (hasDragged) {
          const sourcePos = dragSourcePosRef.current;
          const indicator = dropIndicatorRef.current;
          if (indicator && sourcePos !== null && editor) {
            moveTopLevelBlockToPosition(editor, sourcePos, indicator.targetIndex, indicator.placement);
          }
        }
        cancelDrag();
      };

      const handleKeyDown = (ke: KeyboardEvent) => {
        if (ke.key === "Escape") {
          cancelDrag();
        }
      };

      dragListenersRef.current = {
        mousemove: handleMouseMove,
        mouseup: handleMouseUp,
        keydown: handleKeyDown,
      };

      document.addEventListener("mousemove", handleMouseMove);
      document.addEventListener("mouseup", handleMouseUp);
      document.addEventListener("keydown", handleKeyDown);
    },
    [getPos, editor, scrollContainerRef, cancelDrag],
  );

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (dragListenersRef.current) {
        document.removeEventListener("mousemove", dragListenersRef.current.mousemove);
        document.removeEventListener("mouseup", dragListenersRef.current.mouseup);
        document.removeEventListener("keydown", dragListenersRef.current.keydown);
      }
    };
  }, []);

  return (
    <div ref={containerRef} className="notion-drag-handle-container">
      {activeHandle && !isDragging && (
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
            onDragStart={handleDragStart}
            onHideCancel={cancelHide}
            didDragRef={didDragRef}
          />
        </div>
      )}
      {isDragging && dropIndicator && (
        <div
          className="notion-drop-indicator"
          style={{
            top: dropIndicator.top - 1.5,
            left: 0,
            right: 0,
          }}
        >
          <div className="notion-drop-indicator-dot" />
          <div className="notion-drop-indicator-line" />
        </div>
      )}
    </div>
  );
}
