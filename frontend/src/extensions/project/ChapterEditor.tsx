"use client";

import {
  Bot,
  ChevronLeft,
  FileText,
  Lock,
  Loader2,
  Send,
  Unlock,
  User,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { projectApi } from "@/extensions/project/api";
import type { ReportOutline } from "@/extensions/project/types";

interface ChapterEditorProps {
  projectId: string;
  chapterId: string;
}

interface AiMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
}

export function ChapterEditor({ projectId, chapterId }: ChapterEditorProps) {
  const [outline, setOutline] = useState<ReportOutline[]>([]);
  const [content, setContent] = useState("");
  const [chapterTitle, setChapterTitle] = useState("");
  const [lastSaved, setLastSaved] = useState<string>("尚未保存");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [aiMessages, setAiMessages] = useState<AiMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content: "你好！我是 AI 写作助手。我可以帮你润色文字、扩展段落、检查规范引用，或回答关于报告编写的任何问题。",
    },
  ]);
  const [aiInput, setAiInput] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const currentChapter = useMemo(
    () => outline.find((c) => c.id === chapterId),
    [outline, chapterId],
  );

  const wordCount = useMemo(() => content.length, [content]);
  const wordTarget = currentChapter?.wordCountTarget ?? 3000;
  const progressPercent = useMemo(
    () => Math.min(Math.round((wordCount / wordTarget) * 100), 100),
    [wordCount, wordTarget],
  );

  // Load outline from API
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      try {
        const data = await projectApi.getOutline(projectId);
        if (!cancelled) setOutline(data);
      } catch {
        // Backend not available — keep empty outline
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [projectId]);

  // Set chapter title from outline data
  useEffect(() => {
    if (currentChapter) {
      setChapterTitle(currentChapter.title);
    }
  }, [currentChapter]);

  // Auto-save with debounce (3 seconds) via updateOutline
  const triggerAutoSave = useCallback(() => {
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current);
    }
    saveTimerRef.current = setTimeout(async () => {
      if (!currentChapter) return;
      setSaving(true);
      try {
        await projectApi.updateOutline(projectId, chapterId, {
          wordCountCurrent: content.length,
        });
        const now = new Date();
        const timeStr = `${now.getHours().toString().padStart(2, "0")}:${now.getMinutes().toString().padStart(2, "0")}:${now.getSeconds().toString().padStart(2, "0")}`;
        setLastSaved(`自动保存于 ${timeStr}`);
      } catch {
        setLastSaved("保存失败");
      } finally {
        setSaving(false);
      }
    }, 3000);
  }, [projectId, chapterId, content.length, currentChapter]);

  // Cleanup timer on unmount
  useEffect(() => {
    return () => {
      if (saveTimerRef.current) {
        clearTimeout(saveTimerRef.current);
      }
    };
  }, []);

  const handleContentChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      setContent(e.target.value);
      triggerAutoSave();
    },
    [triggerAutoSave],
  );

  const handleTitleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const newTitle = e.target.value;
      setChapterTitle(newTitle);
      // Debounced title save
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      saveTimerRef.current = setTimeout(async () => {
        try {
          await projectApi.updateOutline(projectId, chapterId, { title: newTitle });
        } catch {
          // Title save failed silently
        }
      }, 3000);
    },
    [projectId, chapterId],
  );

  const handleAiSend = useCallback(() => {
    const trimmed = aiInput.trim();
    if (!trimmed || aiLoading) return;
    const userMsg: AiMessage = {
      id: `m-${Date.now()}`,
      role: "user",
      content: trimmed,
    };
    setAiMessages((prev) => [...prev, userMsg]);
    setAiInput("");
    setAiLoading(true);

    // TODO: Replace with real AI API streaming call
    // For now, show a placeholder response after a short delay
    setTimeout(() => {
      const aiResponse: AiMessage = {
        id: `m-${Date.now()}-resp`,
        role: "assistant",
        content: "此功能需要接入 AI 后端服务，目前为占位回复。连接 AI 服务后，我将能帮你润色文字、检查规范引用等。",
      };
      setAiMessages((prev) => [...prev, aiResponse]);
      setAiLoading(false);
    }, 1000);
  }, [aiInput, aiLoading]);

  const handleAiKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleAiSend();
      }
    },
    [handleAiSend],
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground text-sm gap-2">
        <Loader2 className="h-4 w-4 animate-spin" />
        加载章节内容...
      </div>
    );
  }

  return (
    <TooltipProvider delayDuration={300}>
      <div className="flex flex-col h-full bg-muted">
        {/* Top toolbar */}
        <header className="bg-background border-b border-border h-14 flex items-center px-4 shrink-0 gap-4">
          <Link href={`/projects/${projectId}`}>
            <Button variant="ghost" size="icon" className="shrink-0">
              <ChevronLeft className="h-4 w-4" />
            </Button>
          </Link>

          <Input
            value={chapterTitle}
            onChange={handleTitleChange}
            className="h-8 border-0 shadow-none bg-transparent text-base font-medium hover:bg-muted/50 focus-visible:bg-muted/50 px-1 max-w-xs"
          />

          {/* Status area */}
          <div className="ml-auto flex items-center gap-2">
            {saving && (
              <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
            )}

            <Tooltip>
              <TooltipTrigger>
                <Unlock className="h-4 w-4 text-muted-foreground" />
              </TooltipTrigger>
              <TooltipContent>编辑功能已就绪</TooltipContent>
            </Tooltip>

            <span className="text-xs text-muted-foreground whitespace-nowrap">
              已写 {wordCount} / 目标 {wordTarget} 字
            </span>
          </div>
        </header>

        {/* Main content area */}
        <div className="flex flex-1 overflow-hidden">
          {/* Left sidebar: chapter outline */}
          <aside className="w-52 shrink-0 border-r border-border bg-background overflow-y-auto p-3">
            <div className="text-xs font-medium text-muted-foreground mb-2 px-2">
              章节目录
            </div>
            <div className="flex flex-col gap-0.5">
              {outline.map((ch) => (
                <Link
                  key={ch.id}
                  href={`/projects/${projectId}/chapter/${ch.id}`}
                  className={cn(
                    "flex items-center gap-2 px-2 py-1.5 rounded-lg text-sm transition-colors",
                    ch.id === chapterId
                      ? "bg-primary/10 text-primary font-medium"
                      : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
                  )}
                >
                  <FileText className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">{ch.title}</span>
                </Link>
              ))}
              {outline.length === 0 && (
                <span className="text-xs text-muted-foreground px-2 py-4">
                  暂无章节大纲
                </span>
              )}
            </div>
          </aside>

          {/* Center: editor */}
          <div className="flex-1 overflow-y-auto bg-background">
            <div className="max-w-3xl mx-auto py-8 px-6">
              <textarea
                className="w-full min-h-[60vh] resize-none border-0 bg-transparent p-0 text-base leading-relaxed text-foreground outline-none placeholder:text-muted-foreground/50"
                style={{ fontFamily: "'Fira Sans', system-ui, sans-serif" }}
                placeholder="开始编写报告内容..."
                value={content}
                onChange={handleContentChange}
              />
            </div>
          </div>

          {/* Right sidebar: AI assistant */}
          <aside className="w-80 shrink-0 border-l border-border bg-muted/30 overflow-y-auto flex flex-col">
            {/* AI header */}
            <div className="flex items-center gap-2 px-3 py-3 border-b border-border shrink-0">
              <Bot className="h-4 w-4 text-primary" />
              <span className="text-sm font-medium">AI 写作助手</span>
            </div>

            {/* Messages list */}
            <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-3">
              {aiMessages.map((msg) => (
                <div
                  key={msg.id}
                  className={cn(
                    "flex gap-2",
                    msg.role === "user" ? "justify-end" : "justify-start",
                  )}
                >
                  {msg.role === "assistant" && (
                    <div className="h-6 w-6 rounded-full bg-primary/10 flex items-center justify-center shrink-0 mt-0.5">
                      <Bot className="h-3.5 w-3.5 text-primary" />
                    </div>
                  )}
                  <div
                    className={cn(
                      "rounded-lg px-3 py-2 text-sm leading-relaxed max-w-[85%] whitespace-pre-wrap",
                      msg.role === "user"
                        ? "bg-primary text-primary-foreground"
                        : "bg-background border border-border text-foreground",
                    )}
                  >
                    {msg.content}
                  </div>
                  {msg.role === "user" && (
                    <div className="h-6 w-6 rounded-full bg-primary/20 flex items-center justify-center shrink-0 mt-0.5">
                      <User className="h-3.5 w-3.5 text-primary" />
                    </div>
                  )}
                </div>
              ))}
              {aiLoading && (
                <div className="flex gap-2 justify-start">
                  <div className="h-6 w-6 rounded-full bg-primary/10 flex items-center justify-center shrink-0 mt-0.5">
                    <Bot className="h-3.5 w-3.5 text-primary" />
                  </div>
                  <div className="rounded-lg px-3 py-2 text-sm bg-background border border-border text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin inline mr-1" />
                    思考中...
                  </div>
                </div>
              )}
            </div>

            {/* AI input */}
            <div className="flex gap-2 p-3 border-t border-border shrink-0">
              <Input
                value={aiInput}
                onChange={(e) => setAiInput(e.target.value)}
                onKeyDown={handleAiKeyDown}
                placeholder="提问或指令..."
                className="text-sm"
              />
              <Button size="icon" onClick={handleAiSend} disabled={!aiInput.trim() || aiLoading}>
                <Send className="h-4 w-4" />
              </Button>
            </div>
          </aside>
        </div>

        {/* Bottom status bar */}
        <footer className="bg-background border-t border-border h-8 flex items-center px-4 text-xs text-muted-foreground shrink-0 gap-4">
          <span>已写 {wordCount} 字</span>

          <div className="flex items-center gap-2 flex-1 justify-center">
            <Progress value={progressPercent} className="w-32 h-1.5" />
            <span>{progressPercent}%</span>
          </div>

          <span>{lastSaved}</span>
        </footer>
      </div>
    </TooltipProvider>
  );
}
