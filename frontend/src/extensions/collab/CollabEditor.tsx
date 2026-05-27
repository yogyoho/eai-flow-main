"use client";

import { forwardRef } from "react";
import { BlockNoteEditor } from "./BlockNoteEditor";
import type { BlockNoteEditorRef } from "./BlockNoteEditor";

export type { BlockNoteEditorRef as CollabEditorRef };

interface CollabEditorProps {
  documentId: string;
  initialContent?: string;
  onChange?: (content: string) => void;
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
