"use client";

import { useEffect, useRef, useState } from "react";

import type { ProjectIdentity } from "@/extensions/project/tabRegistry";
import type { ReportProject } from "@/extensions/project/types";
import type { AIDocument } from "@/extensions/types";

import ProjectDocListPanel from "../../docmgr/ProjectDocListPanel";
import { DocumentEditor, type ProjectFileRef } from "../../docmgr/DocumentManagement";

import { DocCollabView } from "./DocCollabView";


interface EditorTabProps {
	project: ReportProject;
	projectId: string;
	onRefresh: () => void;
	identity: ProjectIdentity | null;
	visibleChapterIds?: string[];
}

// EAI-CUSTOM: 双存储对账——章节「编辑」按钮调 openChapter 后把文档写入
// sessionStorage "openChapterDoc"，EditorTab 挂载时读取并自动打开，
// 使 agent 通过 MCP write_chapter 写入的章节内容能在编辑 Tab 直接编辑。
export function EditorTab({ project, projectId }: EditorTabProps) {
	const [selectedDoc, setSelectedDoc] = useState<AIDocument | null>(null);
	const appliedRef = useRef(false);

	useEffect(() => {
		if (appliedRef.current) return;
		try {
			const raw = sessionStorage.getItem("openChapterDoc");
			if (raw) {
				const doc = JSON.parse(raw) as Record<string, unknown>;
				// 后端 openChapter 返回 _doc_info，用 id（=document_id）构造 AIDocument
				const docId = doc.id ?? doc.document_id;
				if (docId) {
					setSelectedDoc({
						id: String(docId),
						user_id: "",
						title: String(doc.title ?? ""),
						content: typeof doc.content === "string" ? doc.content : "",
						folder: String(doc.folder ?? "project-chapters"),
						is_starred: false,
						is_shared: false,
						status: String(doc.status ?? "active"),
						doc_type: (doc.doc_type as AIDocument["doc_type"]) ?? "document",
						project_id: doc.project_id ? String(doc.project_id) : projectId,
						source_thread_id: doc.source_thread_id ? String(doc.source_thread_id) : undefined,
						file_ref_path: doc.file_ref_path ? String(doc.file_ref_path) : null,
						file_size: typeof doc.file_size === "number" ? doc.file_size : null,
						file_mime: doc.file_mime ? String(doc.file_mime) : null,
						created_at: String(doc.created_at ?? new Date().toISOString()),
						updated_at: String(doc.updated_at ?? new Date().toISOString()),
					});
				}
				sessionStorage.removeItem("openChapterDoc");
			}
		} catch {
			// sessionStorage 解析失败则静默回退到文档列表
		}
		appliedRef.current = true;
	}, [projectId]);

	if (selectedDoc) {
		// EAI-CUSTOM (bug-1145 根因④ Surface A): proj/ 前缀 = 无 AIDocument 行的 outputs 虚拟文件，
		// DocCollabView（按 AIDocument id 的 Hocuspocus 协同）打不开；复用 DocumentEditor 走跨用户
		// readProjectOutput/saveProjectContent 直读/写磁盘（单人编辑，file_ref 磁盘为真）。
		if (selectedDoc.id.startsWith("proj/")) {
			const projectFile: ProjectFileRef = {
				project_id: selectedDoc.project_id ?? "",
				thread_id: selectedDoc.source_thread_id ?? "",
				rel_path: selectedDoc.file_ref_path ?? "",
				title: selectedDoc.title,
				member: selectedDoc.folder ?? "",
			};
			return (
				<DocumentEditor
					docId={null}
					personalFile={null}
					projectFile={projectFile}
					onBack={() => setSelectedDoc(null)}
				/>
			);
		}
		return (
			<DocCollabView
				doc={selectedDoc}
				projectId={projectId}
				onBack={() => setSelectedDoc(null)}
			/>
		);
	}

	return (
		<ProjectDocListPanel
			projectId={projectId}
			onSelectDoc={setSelectedDoc}
		/>
	);
}
