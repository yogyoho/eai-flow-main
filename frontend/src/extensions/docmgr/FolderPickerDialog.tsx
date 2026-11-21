"use client";

import { FolderPlus, FolderOpen } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

interface FolderPickerDialogProps {
  folders: string[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSelect: (folder: string) => void;
  onCreateFolder?: (folder: string) => void;
  title?: string;
}

export default function FolderPickerDialog({
  folders,
  open,
  onOpenChange,
  onSelect,
  onCreateFolder,
  title = "移动到文件夹",
}: FolderPickerDialogProps) {
  const [newFolderName, setNewFolderName] = useState("");
  const [showNewFolder, setShowNewFolder] = useState(false);

  const handleCreate = () => {
    if (!newFolderName.trim()) return;
    onCreateFolder?.(newFolderName.trim());
    setNewFolderName("");
    setShowNewFolder(false);
  };

  const handleSelect = (folder: string) => {
    onSelect(folder);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>选择目标文件夹</DialogDescription>
        </DialogHeader>
        <div className="max-h-60 space-y-0.5 overflow-y-auto">
          {folders.map((f) => (
            <button
              key={f}
              onClick={() => handleSelect(f)}
              className="text-foreground hover:bg-muted flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors"
            >
              <FolderOpen className="text-muted-foreground h-4 w-4" />
              {f}
            </button>
          ))}
          {folders.length === 0 && (
            <p className="text-muted-foreground py-4 text-center text-sm">
              暂无文件夹
            </p>
          )}
        </div>
        {showNewFolder ? (
          <div className="flex items-center gap-2">
            <Input
              autoFocus
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              placeholder="文件夹名称"
              className="flex-1"
            />
            <Button
              size="sm"
              onClick={handleCreate}
              disabled={!newFolderName.trim()}
            >
              创建
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setShowNewFolder(false);
                setNewFolderName("");
              }}
            >
              取消
            </Button>
          </div>
        ) : (
          <Button
            variant="outline"
            size="sm"
            className="w-full"
            onClick={() => setShowNewFolder(true)}
          >
            <FolderPlus className="h-4 w-4" />
            新建文件夹
          </Button>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
