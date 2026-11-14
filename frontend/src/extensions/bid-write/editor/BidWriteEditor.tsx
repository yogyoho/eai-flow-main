// EAI-CUSTOM 批廿六 M0——PM EditorView React 壳:useEffect 建观(SSR 安全)、
// 400ms 防抖 serialize 回调、undo/redo/serializeNow 命令柄(方案 §三/§六)。
"use client";

import { redo as redoCmd, undo as undoCmd } from "prosemirror-history";
import { type Transaction } from "prosemirror-state";
import { EditorView } from "prosemirror-view";
import {
  forwardRef,
  useImperativeHandle,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  type ConstraintViolation,
} from "@/extensions/bid-write/editor/constraints";
import {
  applyAssertionStates,
  summarize,
  type AssertPayload,
  type AssertSummary,
} from "@/extensions/bid-write/editor/decor";
import { serializeDoc } from "@/extensions/bid-write/editor/doc";
import { type AstJsonNode } from "@/extensions/bid-write/editor/schema.gen";
import {
  createBidWriteEditorState,
  type OnProvenanceJump,
} from "@/extensions/bid-write/editor/state";

export interface BidWriteEditorFlags {
  canUndo: boolean;
  canRedo: boolean;
}

export interface BidWriteEditorHandle {
  undo(): void;
  redo(): void;
  serializeNow(): AstJsonNode | null;
}

/** 断言执行器(M2 演示=editorLocalAssert;真执行器同形替换)。null/抛错=校验未完成 */
export type AssertRunner = (ast: AstJsonNode) => AssertPayload | null;

interface BidWriteEditorProps {
  initialAst: AstJsonNode;
  onDocChange?: (ast: AstJsonNode, flags: BidWriteEditorFlags) => void;
  onViolation?: (violation: ConstraintViolation) => void;
  assertRunner?: AssertRunner;
  onAssert?: (summary: AssertSummary | null, error: boolean) => void;
  onProvenanceJump?: OnProvenanceJump;
  debounceMs?: number;
  ariaLabel?: string;
}

export const BidWriteEditor = forwardRef<BidWriteEditorHandle, BidWriteEditorProps>(
  function BidWriteEditor(
    {
      initialAst,
      onDocChange,
      onViolation,
      assertRunner,
      onAssert,
      onProvenanceJump,
      debounceMs = 400,
      ariaLabel = "投标正文编辑器",
    },
    ref,
  ) {
    const placeRef = useRef<HTMLDivElement | null>(null);
    const viewRef = useRef<EditorView | null>(null);
    const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    // latest-ref:守卫/断言回调每渲染刷新,视图不因回调身份重建
    const onViolationRef = useRef(onViolation);
    onViolationRef.current = onViolation;
    const assertRunnerRef = useRef(assertRunner);
    assertRunnerRef.current = assertRunner;
    const onAssertRef = useRef(onAssert);
    onAssertRef.current = onAssert;
    const onProvenanceJumpRef = useRef(onProvenanceJump);
    onProvenanceJumpRef.current = onProvenanceJump;
    const [ready, setReady] = useState(false);

    // 断言侧信道(§六):serialize→runner→assert:apply 纯装饰回写;runner 抛错/
    // null → onAssert(null, true)=「校验未完成」——绝不默认放行。
    const runAssert = (view: EditorView) => {
      try {
        const payload = assertRunnerRef.current
          ? assertRunnerRef.current(serializeDoc(view.state.doc))
          : null;
        if (payload) applyAssertionStates(view, payload);
        onAssertRef.current?.(payload ? summarize(payload) : null, false);
      } catch {
        onAssertRef.current?.(null, true);
      }
    };

    useEffect(() => {
      const place = placeRef.current;
      if (!place) return;
      const state = createBidWriteEditorState(initialAst, {
        onViolation: (v) => onViolationRef.current?.(v),
        onProvenanceJump: (hit) => onProvenanceJumpRef.current?.(hit),
      });
      const view = new EditorView(place, {
        state,
        dispatchTransaction(tr: Transaction) {
          view.updateState(view.state.apply(tr));
          if (timerRef.current) clearTimeout(timerRef.current);
          timerRef.current = setTimeout(() => {
            onDocChange?.(serializeDoc(view.state.doc), {
              canUndo: undoCmd(view.state, undefined),
              canRedo: redoCmd(view.state, undefined),
            });
            runAssert(view);
          }, debounceMs);
        },
      });
      viewRef.current = view;
      runAssert(view);
      setReady(true);
      return () => {
        if (timerRef.current) clearTimeout(timerRef.current);
        view.destroy();
        viewRef.current = null;
        setReady(false);
      };
      // initialAst 由父级 useMemo 钉住;变更即重建视图(M0 无外部写入通道)
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [initialAst]);

    useImperativeHandle(
      ref,
      () => ({
        undo() {
          const view = viewRef.current;
          if (view) undoCmd(view.state, (tr) => view.dispatch(tr));
        },
        redo() {
          const view = viewRef.current;
          if (view) redoCmd(view.state, (tr) => view.dispatch(tr));
        },
        serializeNow() {
          const view = viewRef.current;
          return view ? serializeDoc(view.state.doc) : null;
        },
      }),
      [],
    );

    return (
      <div
        ref={placeRef}
        className="bwe-editor"
        role="textbox"
        aria-multiline="true"
        aria-label={ariaLabel}
        aria-busy={!ready}
      />
    );
  },
);
