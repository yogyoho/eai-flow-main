"use client";

import {
  Bot,
  ChevronLeft,
  FileText,
  Lock,
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

interface ChapterEditorProps {
  projectId: string;
  chapterId: string;
}

interface ChapterOutline {
  id: string;
  title: string;
  wordCountCurrent: number;
  wordCountTarget: number;
}

interface AiMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
}

const MOCK_CHAPTERS: ChapterOutline[] = [
  { id: "ch-1", title: "第一章 概述", wordCountCurrent: 1200, wordCountTarget: 2000 },
  { id: "ch-2", title: "第二章 工程分析", wordCountCurrent: 3500, wordCountTarget: 5000 },
  { id: "ch-3", title: "第三章 环境质量现状", wordCountCurrent: 800, wordCountTarget: 4000 },
  { id: "ch-4", title: "第四章 环境影响预测", wordCountCurrent: 0, wordCountTarget: 6000 },
  { id: "ch-5", title: "第五章 环保措施", wordCountCurrent: 2100, wordCountTarget: 3000 },
  { id: "ch-6", title: "第六章 结论与建议", wordCountCurrent: 0, wordCountTarget: 2000 },
];

const MOCK_AI_MESSAGES: AiMessage[] = [
  {
    id: "m1",
    role: "assistant",
    content: "你好！我是 AI 写作助手。我可以帮你润色文字、扩展段落、检查规范引用，或回答关于报告编写的任何问题。",
  },
  {
    id: "m2",
    role: "user",
    content: "请帮我检查“工程分析”这一章是否涵盖了环境影响评价技术导则要求的主要分析内容。",
  },
  {
    id: "m3",
    role: "assistant",
    content: "根据 HJ 2.4-2009 技术导则，工程分析章节应包含：\n1. 建设项目概况\n2. 工艺流程及产污环节分析\n3. 污染源强核算\n4. 清洁生产水平分析\n\n你当前的第二章已涵盖前两项，建议补充污染源强核算和清洁生产水平分析。",
  },
];

export function ChapterEditor({ projectId, chapterId }: ChapterEditorProps) {
  const [chapters] = useState<ChapterOutline[]>(MOCK_CHAPTERS);
  const [content, setContent] = useState("");
  const [chapterTitle, setChapterTitle] = useState("");
  const [lastSaved, setLastSaved] = useState<string>("尚未保存");
  const [aiMessages, setAiMessages] = useState<AiMessage[]>(MOCK_AI_MESSAGES);
  const [aiInput, setAiInput] = useState("");
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const currentChapter = useMemo(
    () => chapters.find((c) => c.id === chapterId),
    [chapters, chapterId],
  );

  const wordCount = useMemo(() => content.length, [content]);
  const wordTarget = currentChapter?.wordCountTarget ?? 3000;
  const progressPercent = useMemo(
    () => Math.min(Math.round((wordCount / wordTarget) * 100), 100),
    [wordCount, wordTarget],
  );

  // Set chapter title from mock data
  useEffect(() => {
    if (currentChapter) {
      setChapterTitle(currentChapter.title);
    }
  }, [currentChapter]);

  // Auto-save with debounce (3 seconds)
  const triggerAutoSave = useCallback(() => {
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current);
    }
    saveTimerRef.current = setTimeout(() => {
      const now = new Date();
      const timeStr = `${now.getHours().toString().padStart(2, "0")}:${now.getMinutes().toString().padStart(2, "0")}:${now.getSeconds().toString().padStart(2, "0")}`;
      setLastSaved(`自动保存于 ${timeStr}`);
    }, 3000);
  }, []);

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
      setChapterTitle(e.target.value);
    },
    [],
  );

  const handleAiSend = useCallback(() => {
    const trimmed = aiInput.trim();
    if (!trimmed) return;
    const userMsg: AiMessage = {
      id: `m-${Date.now()}`,
      role: "user",
      content: trimmed,
    };
    setAiMessages((prev) => [...prev, userMsg]);
    setAiInput("");
  }, [aiInput]);

  const handleAiKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleAiSend();
      }
    },
    [handleAiSend],
  );

  // Mock: the first chapter is locked by current user, others by other users
  const isLockedByMe = chapterId === "ch-2";
  const lockedByUser = isLockedByMe ? null : "张三";

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

          {/* Lock status */}
          <div className="ml-auto flex items-center gap-2">
            {isLockedByMe ? (
              <Tooltip>
                <TooltipTrigger>
                  <Lock className="h-4 w-4 text-green-600" />
                </TooltipTrigger>
                <TooltipContent>你正在编辑此章节</TooltipContent>
              </Tooltip>
            ) : lockedByUser ? (
              <Tooltip>
                <TooltipTrigger>
                  <Lock className="h-4 w-4 text-destructive" />
                </TooltipTrigger>
                <TooltipContent>{lockedByUser} 正在编辑此章节</TooltipContent>
              </Tooltip>
            ) : (
              <Tooltip>
                <TooltipTrigger>
                  <Unlock className="h-4 w-4 text-muted-foreground" />
                </TooltipTrigger>
                <TooltipContent>无人锁定，可自由编辑</TooltipContent>
              </Tooltip>
            )}

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
              {chapters.map((ch) => (
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
              <Button size="icon" onClick={handleAiSend} disabled={!aiInput.trim()}>
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
