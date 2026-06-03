"use client";

import { use } from "react";

import { TemplateEditorPage } from "../components/TemplateEditorPage";

export default function EditTemplatePage({ params }: { params: Promise<{ templateId: string }> }) {
  const { templateId } = use(params);
  return <TemplateEditorPage templateId={templateId} />;
}
