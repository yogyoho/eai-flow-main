"use client"

import { useState } from "react"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"

interface NewSubFolderDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  parentId: string | null
  projectId?: string
  onSubmit: (name: string, parentId: string | null, projectId?: string) => Promise<void>
}

export function NewSubFolderDialog({ open, onOpenChange, parentId, projectId, onSubmit }: NewSubFolderDialogProps) {
  const [name, setName] = useState("")
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async () => {
    if (!name.trim()) return
    setSubmitting(true)
    try {
      await onSubmit(name.trim(), parentId, projectId)
      setName("")
      onOpenChange(false)
    } catch (err) {
      console.error("Failed to create folder:", err)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[400px]">
        <DialogHeader>
          <DialogTitle>新建子文件夹</DialogTitle>
        </DialogHeader>
        <input
          className="w-full rounded-md border border-gray-600 bg-transparent px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          placeholder="输入文件夹名称"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
          autoFocus
        />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={handleSubmit} disabled={!name.trim() || submitting}>
            {submitting ? "创建中..." : "创建"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
