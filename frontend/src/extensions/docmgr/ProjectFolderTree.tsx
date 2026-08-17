"use client";

import {
  FolderSync,
  Plus,
  MoreHorizontal,
  Pencil,
  Trash2,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { useState, useRef, useEffect } from "react";

import type { FolderNode } from "@/extensions/api";
import { cn } from "@/lib/utils";

import { NewSubFolderDialog } from "./NewSubFolderDialog";

interface ProjectFolderTreeProps {
  folders: FolderNode[];
  expandedKeys: Set<string>;
  onToggleExpand: (folderId: string) => void;
  onSelectFolder: (folderId: string, folderName: string) => void;
  onCreateFolder: (
    name: string,
    parentId: string | null,
    projectId?: string,
  ) => Promise<void>;
  onRenameFolder: (folderId: string, name: string) => Promise<void>;
  onDeleteFolder: (folderId: string) => Promise<void>;
  activeFolderId?: string | null;
}

export function ProjectFolderTree({
  folders,
  expandedKeys,
  onToggleExpand,
  onSelectFolder,
  onCreateFolder,
  onRenameFolder,
  onDeleteFolder,
  activeFolderId,
}: ProjectFolderTreeProps) {
  return (
    <div className="mt-1 space-y-0.5">
      {folders.map((folder) => (
        <FolderNodeComponent
          key={folder.id}
          folder={folder}
          depth={0}
          expandedKeys={expandedKeys}
          onToggleExpand={onToggleExpand}
          onSelectFolder={onSelectFolder}
          onCreateFolder={onCreateFolder}
          onRenameFolder={onRenameFolder}
          onDeleteFolder={onDeleteFolder}
          activeFolderId={activeFolderId}
        />
      ))}
    </div>
  );
}

interface FolderNodeComponentProps {
  folder: FolderNode;
  depth: number;
  expandedKeys: Set<string>;
  onToggleExpand: (folderId: string) => void;
  onSelectFolder: (folderId: string, folderName: string) => void;
  onCreateFolder: (
    name: string,
    parentId: string | null,
    projectId?: string,
  ) => Promise<void>;
  onRenameFolder: (folderId: string, name: string) => Promise<void>;
  onDeleteFolder: (folderId: string) => Promise<void>;
  activeFolderId?: string | null;
}

function FolderNodeComponent({
  folder,
  depth,
  expandedKeys,
  onToggleExpand,
  onSelectFolder,
  onCreateFolder,
  onRenameFolder,
  onDeleteFolder,
  activeFolderId,
}: FolderNodeComponentProps) {
  const [hovered, setHovered] = useState(false);
  const [showMenu, setShowMenu] = useState(false);
  const [showNewDialog, setShowNewDialog] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState(folder.name);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const renameInputRef = useRef<HTMLInputElement>(null);

  const isExpanded = expandedKeys.has(folder.id);
  const isActive = activeFolderId === folder.id;
  const isProjectRoot = folder.parent_id === null && folder.project_id !== null;
  const hasChildren = folder.children.length > 0;

  // Close menu on outside click
  useEffect(() => {
    if (!showMenu) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowMenu(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [showMenu]);

  // Auto-focus rename input
  useEffect(() => {
    if (renaming && renameInputRef.current) {
      renameInputRef.current.focus();
      renameInputRef.current.select();
    }
  }, [renaming]);

  const handleRenameSubmit = async () => {
    const trimmed = renameValue.trim();
    if (!trimmed || trimmed === folder.name) {
      setRenaming(false);
      setRenameValue(folder.name);
      return;
    }
    try {
      await onRenameFolder(folder.id, trimmed);
    } catch {
      setRenameValue(folder.name);
    }
    setRenaming(false);
  };

  const handleDelete = async () => {
    try {
      await onDeleteFolder(folder.id);
    } catch (err) {
      console.error("Delete failed:", err);
    }
    setConfirmDelete(false);
    setShowMenu(false);
  };

  return (
    <>
      <div
        className="group relative"
        style={{ paddingLeft: depth * 12 }}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      >
        <div
          className={cn(
            "flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1.5 text-xs transition-colors",
            isActive
              ? "bg-primary/10 text-primary font-medium"
              : "text-foreground/80 hover:bg-muted",
          )}
          onClick={() => {
            if (hasChildren || isProjectRoot) {
              onToggleExpand(folder.id);
            }
            onSelectFolder(folder.id, folder.name);
          }}
        >
          {/* Expand/collapse arrow */}
          {hasChildren || isProjectRoot ? (
            isExpanded ? (
              <ChevronDown className="text-muted-foreground h-3 w-3 shrink-0" />
            ) : (
              <ChevronRight className="text-muted-foreground h-3 w-3 shrink-0" />
            )
          ) : (
            <span className="w-3 shrink-0" />
          )}

          {/* 协同文件夹图标（项目共享）：lucide FolderSync 线框，区别个人区普通文件夹；展开/折叠由 chevron 表示 */}
          <FolderSync className="h-3.5 w-3.5 shrink-0 text-amber-500" />

          {/* Name or rename input */}
          {renaming ? (
            <input
              ref={renameInputRef}
              className="bg-muted text-foreground focus:ring-primary flex-1 rounded px-1.5 py-0.5 text-xs outline-none focus:ring-1"
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void handleRenameSubmit();
                if (e.key === "Escape") {
                  setRenaming(false);
                  setRenameValue(folder.name);
                }
              }}
              onBlur={handleRenameSubmit}
              onClick={(e) => e.stopPropagation()}
            />
          ) : (
            <span className="flex-1 truncate">{folder.name}</span>
          )}

          {/* Doc count badge */}
          {folder.doc_count > 0 && (
            <span className="text-muted-foreground shrink-0 text-[11px] tabular-nums">
              {folder.doc_count}
            </span>
          )}

          {/* Hover action buttons */}
          {hovered && !renaming && !folder.is_system && (
            <div className="flex shrink-0 items-center gap-px">
              <button
                className="hover:bg-accent text-muted-foreground hover:text-primary flex h-5 w-5 items-center justify-center rounded"
                title="新建子文件夹"
                onClick={(e) => {
                  e.stopPropagation();
                  setShowNewDialog(true);
                }}
              >
                <Plus className="h-3.5 w-3.5" />
              </button>
              <div className="relative" ref={menuRef}>
                <button
                  className="hover:bg-accent text-muted-foreground hover:text-foreground flex h-5 w-5 items-center justify-center rounded"
                  title="更多操作"
                  onClick={(e) => {
                    e.stopPropagation();
                    setShowMenu(!showMenu);
                  }}
                >
                  <MoreHorizontal className="h-3.5 w-3.5" />
                </button>

                {/* Dropdown menu */}
                {showMenu && (
                  <div className="bg-popover border-border absolute top-6 right-0 z-50 min-w-[140px] rounded-lg border py-1 shadow-lg">
                    <button
                      className="text-foreground/80 hover:bg-muted flex w-full items-center gap-2 px-3 py-1.5 text-sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        setShowMenu(false);
                        setRenaming(true);
                        setRenameValue(folder.name);
                      }}
                    >
                      <Pencil className="h-3.5 w-3.5" />
                      重命名
                    </button>
                    {!isProjectRoot && (
                      <>
                        <div className="bg-border my-1 h-px" />
                        <button
                          className="text-destructive hover:bg-muted flex w-full items-center gap-2 px-3 py-1.5 text-sm"
                          onClick={(e) => {
                            e.stopPropagation();
                            setShowMenu(false);
                            setConfirmDelete(true);
                          }}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                          删除
                        </button>
                      </>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Children (recursive) */}
      {isExpanded && hasChildren && (
        <div>
          {folder.children.map((child) => (
            <FolderNodeComponent
              key={child.id}
              folder={child}
              depth={depth + 1}
              expandedKeys={expandedKeys}
              onToggleExpand={onToggleExpand}
              onSelectFolder={onSelectFolder}
              onCreateFolder={onCreateFolder}
              onRenameFolder={onRenameFolder}
              onDeleteFolder={onDeleteFolder}
              activeFolderId={activeFolderId}
            />
          ))}
        </div>
      )}

      {/* New sub-folder dialog */}
      <NewSubFolderDialog
        open={showNewDialog}
        onOpenChange={setShowNewDialog}
        parentId={folder.id}
        projectId={folder.project_id ?? undefined}
        onSubmit={onCreateFolder}
      />

      {/* Delete confirmation */}
      {confirmDelete && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setConfirmDelete(false)}
        >
          <div
            className="bg-popover border-border max-w-sm rounded-lg border p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-foreground mb-2 font-medium">确认删除</h3>
            <p className="text-muted-foreground mb-5 text-sm">
              确定要删除文件夹「{folder.name}」吗？
              {folder.doc_count > 0 && (
                <span className="text-destructive">
                  {" "}
                  包含 {folder.doc_count} 个文档，将全部永久删除。
                </span>
              )}
            </p>
            <div className="flex justify-end gap-2">
              <button
                className="text-muted-foreground hover:text-foreground border-border hover:bg-muted rounded-md border px-4 py-1.5 text-sm transition-colors"
                onClick={() => setConfirmDelete(false)}
              >
                取消
              </button>
              <button
                className="bg-destructive hover:bg-destructive/90 rounded-md px-4 py-1.5 text-sm text-white transition-colors"
                onClick={handleDelete}
              >
                确认删除
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
