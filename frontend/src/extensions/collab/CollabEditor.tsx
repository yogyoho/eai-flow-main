"use client";

import { forwardRef } from "react";
import { BlockNoteEditor } from "./BlockNoteEditor";
import type { BlockNoteEditorRef } from "./BlockNoteEditor";

export type { BlockNoteEditorRef as CollabEditorRef };

interface CollabEditorProps {
  documentId: string;
  initialContent?: string;
  /**
   * Accepted for prop-signature compatibility with DocumentManagement, but NOT
   * forwarded. Collaborative documents persist via Yjs/Hocuspocus
   * (onStoreDocument) — the traditional onChange auto-save used by TiptapEditor
   * does not apply here.
   */
  onChange?: (content: string) => void;
  /** Accepted for prop compatibility but unused — BlockNote manages its own UI. */
  placeholder?: string;
  className?: string;
}

export const CollabEditor = forwardRef<BlockNoteEditorRef, CollabEditorProps>(
  function CollabEditor({ documentId, initialContent, className }, ref) {
    return (
      <div className={className}>
        <BlockNoteEditor
          ref={ref}
          documentId={documentId}
          initialContent={initialContent}
        />
      </div>
    );
  },
);
