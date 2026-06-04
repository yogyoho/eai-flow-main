"use client";

import { ArrowLeft, Link2 } from "lucide-react";
import dynamic from "next/dynamic";
import { useCallback, useState } from "react";

import { Button } from "@/components/ui/button";
import { useVersions } from "@/extensions/collab/useVersions";
import { VersionPanel } from "@/extensions/collab/VersionPanel";
import type { AIDocument } from "@/extensions/types";
import { cn } from "@/lib/utils";

const CollabEditor = dynamic(
	() => import("@/extensions/collab/CollabEditor").then((m) => ({ default: m.CollabEditor })),
	{ ssr: false },
);

// ── Types ──

export interface DocCollabViewProps {
	doc: AIDocument;
	projectId: string;
	onBack: () => void;
}

type SidebarMode = "traceability" | "versions" | null;

// ── Traceability Panel ──

function TraceabilityPanel({ doc, onClose }: { doc: AIDocument; onClose: () => void }) {
	const rows: Array<{ label: string; value: string }> = [
		{ label: "文档 ID", value: doc.id },
		{ label: "类型", value: doc.doc_type === "file_ref" ? "文件引用" : "文档" },
	];
	if (doc.source_thread_id) {
		rows.push({ label: "来源会话", value: doc.source_thread_id });
	}
	if (doc.file_ref_path) {
		rows.push({ label: "文件路径", value: doc.file_ref_path });
	}
	if (doc.file_size != null) {
		const kb = (doc.file_size / 1024).toFixed(1);
		rows.push({ label: "文件大小", value: `${kb} KB` });
	}
	rows.push(
		{ label: "状态", value: doc.status },
		{
			label: "创建时间",
			value: new Date(doc.created_at).toLocaleString("zh-CN", {
				year: "numeric",
				month: "2-digit",
				day: "2-digit",
				hour: "2-digit",
				minute: "2-digit",
			}),
		},
		{
			label: "更新时间",
			value: new Date(doc.updated_at).toLocaleString("zh-CN", {
				year: "numeric",
				month: "2-digit",
				day: "2-digit",
				hour: "2-digit",
				minute: "2-digit",
			}),
		},
	);

	return (
		<div className="w-80 border-l border-border flex flex-col h-full bg-background">
			<div className="p-3 border-b border-border flex items-center justify-between">
				<div className="flex items-center gap-2">
					<Link2 className="w-4 h-4" />
					<span className="font-medium text-sm">溯源信息</span>
				</div>
				<Button size="sm" variant="outline" onClick={onClose}>
					关闭
				</Button>
			</div>

			<div className="flex-1 overflow-y-auto p-3">
				{/* Document title */}
				<div className="mb-4">
					<h3 className="text-sm font-medium break-words">{doc.title}</h3>
				</div>

				{/* Metadata table */}
				<div className="space-y-3">
					{rows.map((row) => (
						<div key={row.label} className="space-y-0.5">
							<span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
								{row.label}
							</span>
							<p className="text-xs text-foreground break-all font-mono">{row.value}</p>
						</div>
					))}
				</div>
			</div>
		</div>
	);
}

// ── Main Component ──

export function DocCollabView({ doc, projectId, onBack }: DocCollabViewProps) {
	const [sidebarMode, setSidebarMode] = useState<SidebarMode>(null);

	const {
		versions,
		loading: versionsLoading,
		createVersion,
		restoreVersion,
		diffResult,
		diffLoading,
		diffVersions,
	} = useVersions(sidebarMode === "versions" ? doc.id : null);

	const toggleSidebar = useCallback(
		(mode: SidebarMode) => {
			setSidebarMode((prev) => (prev === mode ? null : mode));
		},
		[],
	);

	const closeSidebar = useCallback(() => {
		setSidebarMode(null);
	}, []);

	return (
		<div className="flex h-full flex-col">
			{/* ── Top bar ── */}
			<div className="flex items-center gap-2 border-b border-border px-3 py-2 shrink-0">
				<Button variant="ghost" size="icon-sm" onClick={onBack} title="返回">
					<ArrowLeft className="size-4" />
				</Button>

				<span className="flex-1 truncate text-sm font-medium">{doc.title}</span>

				<Button
					variant={sidebarMode === "traceability" ? "secondary" : "ghost"}
					size="sm"
					className={cn("h-7 text-xs px-2.5")}
					onClick={() => toggleSidebar("traceability")}
					title="溯源"
				>
					<Link2 className="size-3.5 mr-1" />
					溯源
				</Button>
			</div>

			{/* ── Content area ── */}
			<div className="flex flex-1 min-h-0">
				{/* Editor */}
				<div className="flex-1 min-h-0">
					<CollabEditor
						documentId={doc.id}
						projectId={projectId}
						className="h-full"
					/>
				</div>

				{/* Sidebar */}
				{sidebarMode === "versions" && (
					<VersionPanel
						versions={versions}
						loading={versionsLoading}
						diffLoading={diffLoading}
						diffResult={diffResult}
						onCreateVersion={async (summary, generateAiSummary, content) => {
							await createVersion(summary, generateAiSummary, content);
						}}
						onRestoreVersion={async (version) => {
							await restoreVersion(version);
						}}
						onPreviewVersion={async () => {
							/* preview handled by version panel internally */
						}}
						onDiffVersions={diffVersions}
						onClose={closeSidebar}
					/>
				)}
				{sidebarMode === "traceability" && (
					<TraceabilityPanel doc={doc} onClose={closeSidebar} />
				)}
			</div>
		</div>
	);
}
