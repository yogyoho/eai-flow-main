"use client"

import { useState, useRef, useEffect } from "react"
import { FolderClosed, FolderOpen, Plus, MoreHorizontal, Pencil, Trash2, ChevronDown, ChevronRight } from "lucide-react"
import { cn } from "@/lib/utils"
import type { FolderNode } from "@/extensions/api"
import { NewSubFolderDialog } from "./NewSubFolderDialog"

interface ProjectFolderTreeProps {
  folders: FolderNode[]
  expandedKeys: Set<string>
  onToggleExpand: (folderId: string) => void
  onSelectFolder: (folderId: string, folderName: string) => void
  onCreateFolder: (name: string, parentId: string | null, projectId?: string) => Promise<void>
  onRenameFolder: (folderId: string, name: string) => Promise<void>
  onDeleteFolder: (folderId: string) => Promise<void>
  activeFolderId?: string | null
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
    <div className="space-y-0.5 mt-1">
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
  )
}

interface FolderNodeComponentProps {
  folder: FolderNode
  depth: number
  expandedKeys: Set<string>
  onToggleExpand: (folderId: string) => void
  onSelectFolder: (folderId: string, folderName: string) => void
  onCreateFolder: (name: string, parentId: string | null, projectId?: string) => Promise<void>
  onRenameFolder: (folderId: string, name: string) => Promise<void>
  onDeleteFolder: (folderId: string) => Promise<void>
  activeFolderId?: string | null
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
  const [hovered, setHovered] = useState(false)
  const [showMenu, setShowMenu] = useState(false)
  const [showNewDialog, setShowNewDialog] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [renameValue, setRenameValue] = useState(folder.name)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  const renameInputRef = useRef<HTMLInputElement>(null)

  const isExpanded = expandedKeys.has(folder.id)
  const isActive = activeFolderId === folder.id
  const isProjectRoot = folder.parent_id === null && folder.project_id !== null
  const hasChildren = folder.children.length > 0

  // Close menu on outside click
  useEffect(() => {
    if (!showMenu) return
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowMenu(false)
      }
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [showMenu])

  // Auto-focus rename input
  useEffect(() => {
    if (renaming && renameInputRef.current) {
      renameInputRef.current.focus()
      renameInputRef.current.select()
    }
  }, [renaming])

  const handleRenameSubmit = async () => {
    const trimmed = renameValue.trim()
    if (!trimmed || trimmed === folder.name) {
      setRenaming(false)
      setRenameValue(folder.name)
      return
    }
    try {
      await onRenameFolder(folder.id, trimmed)
    } catch {
      setRenameValue(folder.name)
    }
    setRenaming(false)
  }

  const handleDelete = async () => {
    try {
      await onDeleteFolder(folder.id)
    } catch (err) {
      console.error("Delete failed:", err)
    }
    setConfirmDelete(false)
    setShowMenu(false)
  }

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
            "flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm cursor-pointer transition-colors",
            isActive
              ? "bg-primary/10 text-primary font-medium"
              : "text-foreground/80 hover:bg-muted",
          )}
          onClick={() => {
            if (hasChildren || isProjectRoot) {
              onToggleExpand(folder.id)
            }
            onSelectFolder(folder.id, folder.name)
          }}
        >
          {/* Expand/collapse arrow */}
          {(hasChildren || isProjectRoot) ? (
            isExpanded
              ? <ChevronDown className="w-3 h-3 shrink-0 text-muted-foreground" />
              : <ChevronRight className="w-3 h-3 shrink-0 text-muted-foreground" />
          ) : (
            <span className="w-3 shrink-0" />
          )}

          {/* Folder icon */}
          {isExpanded && hasChildren
            ? <FolderOpen className="w-4 h-4 shrink-0 text-amber-500" />
            : <FolderClosed className="w-4 h-4 shrink-0 text-amber-500" />
          }

          {/* Name or rename input */}
          {renaming ? (
            <input
              ref={renameInputRef}
              className="flex-1 bg-muted rounded px-1.5 py-0.5 text-sm text-foreground outline-none focus:ring-1 focus:ring-primary"
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleRenameSubmit()
                if (e.key === "Escape") {
                  setRenaming(false)
                  setRenameValue(folder.name)
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
            <span className="text-[11px] text-muted-foreground tabular-nums shrink-0">
              {folder.doc_count}
            </span>
          )}

          {/* Hover action buttons */}
          {hovered && !renaming && !folder.is_system && (
            <div className="flex items-center gap-px shrink-0">
              <button
                className="w-5 h-5 flex items-center justify-center rounded hover:bg-accent text-muted-foreground hover:text-primary"
                title="新建子文件夹"
                onClick={(e) => {
                  e.stopPropagation()
                  setShowNewDialog(true)
                }}
              >
                <Plus className="w-3.5 h-3.5" />
              </button>
              <div className="relative" ref={menuRef}>
                <button
                  className="w-5 h-5 flex items-center justify-center rounded hover:bg-accent text-muted-foreground hover:text-foreground"
                  title="更多操作"
                  onClick={(e) => {
                    e.stopPropagation()
                    setShowMenu(!showMenu)
                  }}
                >
                  <MoreHorizontal className="w-3.5 h-3.5" />
                </button>

                {/* Dropdown menu */}
                {showMenu && (
                  <div className="absolute right-0 top-6 z-50 bg-popover border border-border rounded-lg shadow-lg py-1 min-w-[140px]">
                    <button
                      className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-foreground/80 hover:bg-muted"
                      onClick={(e) => {
                        e.stopPropagation()
                        setShowMenu(false)
                        setRenaming(true)
                        setRenameValue(folder.name)
                      }}
                    >
                      <Pencil className="w-3.5 h-3.5" />重命名
                    </button>
                    {!isProjectRoot && (
                      <>
                        <div className="h-px bg-border my-1" />
                        <button
                          className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-destructive hover:bg-muted"
                          onClick={(e) => {
                            e.stopPropagation()
                            setShowMenu(false)
                            setConfirmDelete(true)
                          }}
                        >
                          <Trash2 className="w-3.5 h-3.5" />删除
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setConfirmDelete(false)}>
          <div className="bg-popover border border-border rounded-lg p-5 max-w-sm shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-foreground font-medium mb-2">确认删除</h3>
            <p className="text-muted-foreground text-sm mb-5">
              确定要删除文件夹「{folder.name}」吗？
              {folder.doc_count > 0 && (
                <span className="text-destructive"> 包含 {folder.doc_count} 个文档，将全部永久删除。</span>
              )}
            </p>
            <div className="flex gap-2 justify-end">
              <button
                className="px-4 py-1.5 text-sm text-muted-foreground hover:text-foreground rounded-md border border-border hover:bg-muted transition-colors"
                onClick={() => setConfirmDelete(false)}
              >
                取消
              </button>
              <button
                className="px-4 py-1.5 text-sm text-white bg-destructive hover:bg-destructive/90 rounded-md transition-colors"
                onClick={handleDelete}
              >
                确认删除
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
