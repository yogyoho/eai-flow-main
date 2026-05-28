"use client";

import { Copy, Link2, Users, CheckCircle2, Loader2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import { docmgrApi } from "../api";
import type { AIDocument } from "../types";

interface ShareDialogProps {
  doc: AIDocument | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export default function ShareDialog({ doc, open, onOpenChange }: ShareDialogProps) {
  const [link, setLink] = useState("");
  const [linkCopied, setLinkCopied] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [targetId, setTargetId] = useState("");
  const [permission, setPermission] = useState<"read" | "edit">("read");
  const [sharing, setSharing] = useState(false);
  const [shareMessage, setShareMessage] = useState<string | null>(null);

  const resetState = () => {
    setLink("");
    setLinkCopied(false);
    setTargetId("");
    setPermission("read");
    setShareMessage(null);
  };

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) resetState();
    onOpenChange(nextOpen);
  };

  const handleGenerateLink = async () => {
    if (!doc) return;
    setGenerating(true);
    try {
      const res = await docmgrApi.shareDocument(doc.id, {
        share_type: "link",
        permission,
      });
      if (res?.share_token) {
        const shareUrl = `${window.location.origin}/shared/${res.share_token}`;
        setLink(shareUrl);
      }
    } catch {
      setShareMessage("生成链接失败");
    } finally {
      setGenerating(false);
    }
  };

  const handleCopyLink = async () => {
    if (!link) return;
    await navigator.clipboard.writeText(link);
    setLinkCopied(true);
    setTimeout(() => setLinkCopied(false), 2000);
  };

  const handleShareToUser = async () => {
    if (!doc || !targetId.trim()) return;
    setSharing(true);
    setShareMessage(null);
    try {
      await docmgrApi.shareDocument(doc.id, {
        share_type: "user",
        share_target_id: targetId.trim(),
        permission,
      });
      setShareMessage("分享成功");
      setTargetId("");
    } catch {
      setShareMessage("分享失败");
    } finally {
      setSharing(false);
    }
  };

  if (!doc) return null;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>分享文档</DialogTitle>
          <DialogDescription className="truncate">{doc.title || "无标题"}</DialogDescription>
        </DialogHeader>
        <Tabs defaultValue="link">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="link" className="flex items-center gap-1.5">
              <Link2 className="w-3.5 h-3.5" />
              通过链接分享
            </TabsTrigger>
            <TabsTrigger value="user" className="flex items-center gap-1.5">
              <Users className="w-3.5 h-3.5" />
              分享给用户
            </TabsTrigger>
          </TabsList>
          <TabsContent value="link" className="space-y-4 mt-4">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1.5">权限</label>
              <div className="flex gap-2">
                <Button
                  variant={permission === "read" ? "default" : "outline"}
                  size="sm"
                  onClick={() => setPermission("read")}
                >
                  只读
                </Button>
                <Button
                  variant={permission === "edit" ? "default" : "outline"}
                  size="sm"
                  onClick={() => setPermission("edit")}
                >
                  可编辑
                </Button>
              </div>
            </div>
            {!link ? (
              <Button className="w-full" onClick={handleGenerateLink} disabled={generating}>
                {generating ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    生成中...
                  </>
                ) : (
                  "生成分享链接"
                )}
              </Button>
            ) : (
              <div className="space-y-2">
                <Input readOnly value={link} className="text-xs" />
                <Button variant="outline" className="w-full" onClick={handleCopyLink}>
                  {linkCopied ? (
                    <>
                      <CheckCircle2 className="w-4 h-4 text-green-500" />
                      链接已复制
                    </>
                  ) : (
                    <>
                      <Copy className="w-4 h-4" />
                      复制链接
                    </>
                  )}
                </Button>
              </div>
            )}
          </TabsContent>
          <TabsContent value="user" className="space-y-4 mt-4">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1.5">用户 ID</label>
              <Input
                value={targetId}
                onChange={(e) => setTargetId(e.target.value)}
                placeholder="输入用户 ID"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1.5">权限</label>
              <div className="flex gap-2">
                <Button
                  variant={permission === "read" ? "default" : "outline"}
                  size="sm"
                  onClick={() => setPermission("read")}
                >
                  只读
                </Button>
                <Button
                  variant={permission === "edit" ? "default" : "outline"}
                  size="sm"
                  onClick={() => setPermission("edit")}
                >
                  可编辑
                </Button>
              </div>
            </div>
            <Button className="w-full" onClick={handleShareToUser} disabled={sharing || !targetId.trim()}>
              {sharing ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  分享中...
                </>
              ) : (
                "分享"
              )}
            </Button>
          </TabsContent>
        </Tabs>
        {shareMessage && (
          <p className={`text-xs text-center ${shareMessage.includes("失败") ? "text-destructive" : "text-green-600"}`}>
            {shareMessage}
          </p>
        )}
      </DialogContent>
    </Dialog>
  );
}
