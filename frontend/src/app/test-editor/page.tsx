"use client";

import { useCreateBlockNote, BlockNoteViewRaw } from "@blocknote/react";

export default function TestEditorPage() {
  const editor = useCreateBlockNote({}, []);

  if (!editor) return <div>Loading...</div>;

  return (
    <div style={{ padding: 40 }}>
      <h1>BlockNote Test</h1>
      <BlockNoteViewRaw editor={editor} />
    </div>
  );
}
