"use client";

import { forwardRef } from "react";

import { BlockNoteEditor } from "./BlockNoteEditor";
import type { BlockNoteEditorRef } from "./BlockNoteEditor";

export type { BlockNoteEditorRef as CollabEditorRef };

interface CollabEditorProps {
  documentId: string;
  initialContent?: string;
  projectId?: string;
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
  /**
   * Optional list of block IDs to show in the outline panel.
   * When provided, only headings whose block ID is in this list will be displayed.
   * Used to restrict visibility based on chapter write permissions.
   */
  visibleChapterIds?: string[];
}

export const CollabEditor = forwardRef<BlockNoteEditorRef, CollabEditorProps>(
  function CollabEditor({ documentId, initialContent, projectId, className, visibleChapterIds }, ref) {
    return (
      <div className={className} style={{ minHeight: 0, display: "flex", flexDirection: "row" }}>
        <BlockNoteEditor
          ref={ref}
          documentId={documentId}
          initialContent={initialContent}
          projectId={projectId}
          visibleChapterIds={visibleChapterIds}
        />
      </div>
    );
  },
);
