"use client";

import dynamic from "next/dynamic";
import { useMemo, useState } from "react";

import {
	CheckCircle2,
	ChevronDown,
	ChevronRight,
	Clock,
	Eye,
	FileText,
	Lock,
	Pencil,
	PanelLeftClose,
	PanelLeftOpen,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

import type { ProjectChapter, ReportProject } from "@/extensions/project/types";
import type { ProjectIdentity } from "@/extensions/project/tabRegistry";

const CollabEditor = dynamic(
	() => import("@/extensions/collab/CollabEditor").then((m) => ({ default: m.CollabEditor })),
	{ ssr: false, loading: () => <EditorSkeleton /> },
);

interface EditorTabProps {
	project: ReportProject;
	projectId: string;
	onRefresh: () => void;
	identity: ProjectIdentity | null;
	visibleChapterIds?: string[];
}

// ── Status icon mapping (Lucide, no emoji) ──

const STATUS_ICON_MAP: Record<string, { icon: typeof Clock; className: string }> = {
	not_started: { icon: Clock, className: "text-muted-foreground" },
	pending: { icon: Clock, className: "text-muted-foreground" },
	writing: { icon: Pencil, className: "text-blue-500" },
	in_review: { icon: Eye, className: "text-amber-500" },
	pending_review: { icon: Eye, className: "text-amber-500" },
	approved: { icon: CheckCircle2, className: "text-emerald-500" },
	completed: { icon: CheckCircle2, className: "text-emerald-500" },
	signed: { icon: CheckCircle2, className: "text-emerald-500" },
};

function getStatusIcon(status: string) {
	return STATUS_ICON_MAP[status] ?? { icon: Clock, className: "text-muted-foreground" };
}

// ── Collect all descendant IDs for default-expand ──

function collectIds(chapters: ProjectChapter[]): string[] {
	const ids: string[] = [];
	for (const ch of chapters) {
		ids.push(ch.id);
		if (ch.children?.length) ids.push(...collectIds(ch.children));
	}
	return ids;
}

// ── Recursive tree node ──

interface TreeNodeProps {
	chapter: ProjectChapter;
	depth: number;
	selectedId: string | null;
	onSelect: (id: string) => void;
	expandedIds: Set<string>;
	toggleExpand: (id: string) => void;
	editableIds?: string[];
}

function ChapterTreeNode({
	chapter,
	depth,
	selectedId,
	onSelect,
	expandedIds,
	toggleExpand,
	editableIds,
}: TreeNodeProps) {
	const hasChildren = (chapter.children?.length ?? 0) > 0;
	const isExpanded = expandedIds.has(chapter.id);
	const isSelected = selectedId === chapter.id;
	const isEditable = !editableIds || editableIds.includes(chapter.id);
	const { icon: StatusIcon, className: statusCls } = getStatusIcon(chapter.status);

	return (
		<>
			<button
				type="button"
				onClick={() => {
					onSelect(chapter.id);
					if (hasChildren && !isExpanded) toggleExpand(chapter.id);
				}}
				className={cn(
					"flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-left text-[13px] transition-colors",
					isSelected ? "bg-accent text-accent-foreground font-medium" : "text-foreground/80 hover:bg-accent/50",
					!isEditable && "opacity-50",
				)}
				style={{ paddingLeft: `${depth * 16 + 8}px` }}
			>
				{/* Expand/collapse chevron */}
				{hasChildren ? (
					<span
						role="button"
						tabIndex={0}
						onClick={(e) => {
							e.stopPropagation();
							toggleExpand(chapter.id);
						}}
						onKeyDown={(e) => {
							if (e.key === "Enter" || e.key === " ") {
								e.stopPropagation();
								toggleExpand(chapter.id);
							}
						}}
						className="shrink-0 cursor-pointer rounded p-0.5 hover:bg-accent"
					>
						{isExpanded ? (
							<ChevronDown className="size-3.5 text-muted-foreground" />
						) : (
							<ChevronRight className="size-3.5 text-muted-foreground" />
						)}
					</span>
				) : (
					<span className="w-[22px] shrink-0" />
				)}

				{/* Status icon */}
				<StatusIcon className={cn("size-3.5 shrink-0", statusCls)} />

				{/* Title */}
				<span className="flex-1 truncate">{chapter.title}</span>

				{/* Lock icon for non-editable chapters */}
				{!isEditable && <Lock className="size-3 shrink-0 text-muted-foreground" />}
			</button>

			{/* Children */}
			{hasChildren && isExpanded && (
				<div>
					{chapter.children!.map((child) => (
						<ChapterTreeNode
							key={child.id}
							chapter={child}
							depth={depth + 1}
							selectedId={selectedId}
							onSelect={onSelect}
							expandedIds={expandedIds}
							toggleExpand={toggleExpand}
							editableIds={editableIds}
						/>
					))}
				</div>
			)}
		</>
	);
}

// ── Skeleton ──

function EditorSkeleton() {
	return (
		<div className="flex h-full gap-3 p-4">
			<Skeleton className="h-full w-56 shrink-0" />
			<div className="flex-1 rounded-lg border">
				<Skeleton className="h-full w-full" />
			</div>
		</div>
	);
}

// ── Main component ──

export function EditorTab({ project, projectId, visibleChapterIds }: EditorTabProps) {
	const [selectedChapterId, setSelectedChapterId] = useState<string | null>(null);
	const [outlineOpen, setOutlineOpen] = useState(true);

	// Default-expand first-level chapters
	const [expandedIds, setExpandedIds] = useState<Set<string>>(() => {
		const firstLevel = project.chapters?.map((ch) => ch.id) ?? [];
		return new Set(firstLevel);
	});

	const toggleExpand = (id: string) => {
		setExpandedIds((prev) => {
			const next = new Set(prev);
			if (next.has(id)) next.delete(id);
			else next.add(id);
			return next;
		});
	};

	// Build editable ID list (all descendant IDs from visibleChapterIds + themselves)
	const editableIds = useMemo(() => {
		if (!visibleChapterIds || visibleChapterIds.length === 0) return undefined;
		const allEditable = new Set(visibleChapterIds);
		// Also include children of editable chapters
		const walk = (chapters: ProjectChapter[]) => {
			for (const ch of chapters) {
				if (allEditable.has(ch.id) && ch.children?.length) {
					for (const child of ch.children) allEditable.add(child.id);
					walk(ch.children);
				}
			}
		};
		walk(project.chapters ?? []);
		return Array.from(allEditable);
	}, [visibleChapterIds, project.chapters]);

	const docId = selectedChapterId ? `project-${projectId}-chapter-${selectedChapterId}` : `project-${projectId}`;

	const chapters = project.chapters ?? [];

	return (
		<div className="flex h-full">
			{/* Left outline panel */}
			{outlineOpen && (
				<div className="flex w-56 shrink-0 flex-col border-r border-border/60 bg-muted/10">
					{/* Header */}
					<div className="flex items-center justify-between border-b border-border/40 px-3 py-2">
						<span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
							文档大纲
						</span>
						<Button
							variant="ghost"
							size="icon-sm"
							onClick={() => setOutlineOpen(false)}
							title="收起大纲"
						>
							<PanelLeftClose className="size-4 text-muted-foreground" />
						</Button>
					</div>

					{/* Tree content */}
					<ScrollArea className="flex-1">
						<div className="space-y-0.5 p-2">
							{/* "Full document" button */}
							<button
								type="button"
								onClick={() => setSelectedChapterId(null)}
								className={cn(
									"flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[13px] transition-colors",
									selectedChapterId === null
										? "bg-accent text-accent-foreground font-medium"
										: "text-foreground/80 hover:bg-accent/50",
								)}
							>
								<FileText className="size-3.5 shrink-0 text-muted-foreground" />
								<span>全文</span>
								<span className="ml-auto text-[11px] text-muted-foreground">{chapters.length}</span>
							</button>

							{/* Chapter tree */}
							{chapters.map((ch) => (
								<ChapterTreeNode
									key={ch.id}
									chapter={ch}
									depth={0}
									selectedId={selectedChapterId}
									onSelect={setSelectedChapterId}
									expandedIds={expandedIds}
									toggleExpand={toggleExpand}
									editableIds={editableIds}
								/>
							))}
						</div>
					</ScrollArea>
				</div>
			)}

			{/* Collapsed toggle */}
			{!outlineOpen && (
				<Button
					variant="ghost"
					size="icon-sm"
					onClick={() => setOutlineOpen(true)}
					title="展开大纲"
					className="m-2 shrink-0 self-start"
				>
					<PanelLeftOpen className="size-4 text-muted-foreground" />
				</Button>
			)}

			{/* Editor area */}
			<div className="flex-1 min-h-0">
				<CollabEditor
					documentId={docId}
					projectId={projectId}
					visibleChapterIds={visibleChapterIds}
					className="h-full"
				/>
			</div>
		</div>
	);
}
