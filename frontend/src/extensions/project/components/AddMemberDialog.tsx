"use client";

import { Loader2, UserPlus } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";

import { projectApi } from "@/extensions/project/api";
import { MEMBER_ROLE_LABELS, type MemberRole } from "@/extensions/project/types";

interface AddMemberDialogProps {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAdded: () => void;
}

export function AddMemberDialog({ projectId, open, onOpenChange, onAdded }: AddMemberDialogProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<Array<{ id: string; username: string; fullName?: string }>>([]);
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [newRole, setNewRole] = useState<MemberRole>("member");
  const [adding, setAdding] = useState(false);

  // Reset state on open
  useEffect(() => {
    if (open) {
      setSearchQuery("");
      setSearchResults([]);
      setSelectedUserId(null);
      setNewRole("member");
    }
  }, [open]);

  // Search users with debounce
  useEffect(() => {
    if (!searchQuery.trim()) {
      setSearchResults([]);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const resp = await fetch(`/api/extensions/users/search?keyword=${encodeURIComponent(searchQuery)}`);
        if (resp.ok) {
          const data = await resp.json();
          setSearchResults((data.users ?? data.items ?? []).slice(0, 10));
        }
      } catch {
        /* ignore */
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const handleAdd = async () => {
    if (!selectedUserId) return;
    setAdding(true);
    try {
      await projectApi.addMember(projectId, selectedUserId, newRole);
      onOpenChange(false);
      onAdded();
      toast.success("成员已添加");
    } catch {
      toast.error("添加成员失败");
    } finally {
      setAdding(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>添加成员</DialogTitle>
          <DialogDescription>搜索用户并指定角色</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <Input
            placeholder="搜索用户名..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setSelectedUserId(null);
            }}
          />
          {searchResults.length > 0 && (
            <ScrollArea className="h-40">
              <div className="space-y-0.5">
                {searchResults.map((u) => (
                  <button
                    key={u.id}
                    type="button"
                    onClick={() => {
                      setSelectedUserId(u.id);
                      setSearchQuery(u.username);
                    }}
                    className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors ${
                      selectedUserId === u.id ? "bg-primary/10 text-primary" : "hover:bg-accent/40"
                    }`}
                  >
                    <div className="flex h-6 w-6 items-center justify-center rounded-full bg-muted text-[10px] font-medium">
                      {u.username.charAt(0).toUpperCase()}
                    </div>
                    <span>{u.username}</span>
                    {u.fullName && <span className="text-muted-foreground">({u.fullName})</span>}
                  </button>
                ))}
              </div>
            </ScrollArea>
          )}
          <div className="flex items-center gap-2">
            <Select value={newRole} onValueChange={(v) => setNewRole(v as MemberRole)}>
              <SelectTrigger className="h-8 w-32 text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(MEMBER_ROLE_LABELS)
                  .filter(([key]) => key !== "owner")
                  .map(([key, label]) => (
                    <SelectItem key={key} value={key}>
                      {label}
                    </SelectItem>
                  ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button size="sm" disabled={!selectedUserId || adding} onClick={handleAdd}>
            {adding ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <UserPlus className="h-3 w-3 mr-1" />}
            添加
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
