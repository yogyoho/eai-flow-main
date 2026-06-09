"use client"

import { useState, useRef, useEffect } from "react"
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
    <div className="space-y-0.5">
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
        style={{ paddingLeft: depth * 16 }}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => {
          setHovered(false)
        }}
      >
        <div
          className={`flex items-center gap-1.5 rounded px-2 py-1 text-sm cursor-pointer transition-colors ${
            isActive ? "bg-blue-600/20 text-blue-300" : "text-gray-300 hover:bg-white/5"
          }`}
          onClick={() => {
            if (hasChildren || isProjectRoot) {
              onToggleExpand(folder.id)
            }
            onSelectFolder(folder.id, folder.name)
          }}
        >
          {/* Expand/collapse arrow */}
          {(hasChildren || isProjectRoot) && (
            <span className="text-xs text-gray-500 w-3 shrink-0">
              {isExpanded ? "▼" : "▶"}
            </span>
          )}
          {!hasChildren && !isProjectRoot && <span className="w-3 shrink-0" />}

          {/* Folder icon */}
          <span className="shrink-0">{isExpanded && hasChildren ? "📂" : "📁"}</span>

          {/* Name or rename input */}
          {renaming ? (
            <input
              ref={renameInputRef}
              className="flex-1 bg-gray-700 rounded px-1.5 py-0.5 text-sm text-white outline-none focus:ring-1 focus:ring-blue-500"
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

          {/* Doc count */}
          <span className="text-xs text-gray-500 shrink-0">{folder.doc_count}</span>

          {/* Hover action buttons */}
          {hovered && !renaming && !folder.is_system && (
            <div className="flex items-center gap-0.5 shrink-0">
              <button
                className="w-5 h-5 flex items-center justify-center rounded hover:bg-white/10 text-gray-400 hover:text-blue-400 text-xs"
                title="新建子文件夹"
                onClick={(e) => {
                  e.stopPropagation()
                  setShowNewDialog(true)
                }}
              >
                +
              </button>
              <div className="relative" ref={menuRef}>
                <button
                  className="w-5 h-5 flex items-center justify-center rounded hover:bg-white/10 text-gray-400 hover:text-white text-xs"
                  title="更多操作"
                  onClick={(e) => {
                    e.stopPropagation()
                    setShowMenu(!showMenu)
                  }}
                >
                  ⋯
                </button>

                {/* Dropdown menu */}
                {showMenu && (
                  <div className="absolute right-0 top-6 z-50 bg-gray-800 border border-gray-700 rounded-lg shadow-xl py-1 min-w-[140px]">
                    <button
                      className="w-full px-3 py-1.5 text-left text-sm text-gray-300 hover:bg-white/5"
                      onClick={(e) => {
                        e.stopPropagation()
                        setShowMenu(false)
                        setRenaming(true)
                        setRenameValue(folder.name)
                      }}
                    >
                      ✏️ 重命名
                    </button>
                    {!isProjectRoot && (
                      <>
                        <div className="border-t border-gray-700 my-1" />
                        <button
                          className="w-full px-3 py-1.5 text-left text-sm text-red-400 hover:bg-white/5"
                          onClick={(e) => {
                            e.stopPropagation()
                            setShowMenu(false)
                            setConfirmDelete(true)
                          }}
                        >
                          🗑️ 删除
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
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-4 max-w-sm shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-white font-medium mb-2">确认删除</h3>
            <p className="text-gray-400 text-sm mb-4">
              确定要删除文件夹「{folder.name}」吗？
              {folder.doc_count > 0 && (
                <span className="text-red-400"> 包含 {folder.doc_count} 个文档，将全部永久删除。</span>
              )}
            </p>
            <div className="flex gap-2 justify-end">
              <button
                className="px-3 py-1.5 text-sm text-gray-400 hover:text-white rounded border border-gray-600 hover:border-gray-400"
                onClick={() => setConfirmDelete(false)}
              >
                取消
              </button>
              <button
                className="px-3 py-1.5 text-sm text-white bg-red-600 hover:bg-red-700 rounded"
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
