"use client";

import { useState } from "react";

import type { AIDocument } from "@/extensions/types";

import ProjectDocListPanel from "../../docmgr/ProjectDocListPanel";
import { DocCollabView } from "./DocCollabView";

import type { ReportProject } from "@/extensions/project/types";
import type { ProjectIdentity } from "@/extensions/project/tabRegistry";

interface EditorTabProps {
	project: ReportProject;
	projectId: string;
	onRefresh: () => void;
	identity: ProjectIdentity | null;
	visibleChapterIds?: string[];
}

export function EditorTab({ project, projectId }: EditorTabProps) {
	const [selectedDoc, setSelectedDoc] = useState<AIDocument | null>(null);

	if (selectedDoc) {
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
