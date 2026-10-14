"use client";

/**
 * EAI-CUSTOM: cpa v3 合同文件库（spec 2026-10-14 §1.4）。
 * 视觉语言对齐翻译资产库 AssetLibrary：顶栏 / flash 通知条 / 面包屑 /
 * rounded-lg 单容器（pane 头 + Explorer 树 + 简洁表格）/ 统计底栏。
 * 高保真原型: .wolf/tmp/cpa-v3-prototype.html 屏幕①。
 */

import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  ChevronRight,
  CircleCheck,
  CircleDashed,
  CircleX,
  Download,
  Eye,
  FolderInput,
  FolderPlus,
  ListChecks,
  Loader2,
  MoreHorizontal,
  Pencil,
  Trash2,
  Upload,
  Zap,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import { libraryApi } from "../api";
import {
  useLibraryFiles,
  useLibraryFolders,
  useLibraryMutations,
} from "../hooks";
import type { CpaLibraryFile } from "../types";

import {
  buildFolderTree,
  pathOf,
  ROOT_ID,
  type FolderNode,
} from "./library-tree";

const FILE_TYPES: Record<string, { bg: string; letter: string }> = {
  pdf: { bg: "#B30B00", letter: "A" },
  docx: { bg: "#2B579A", letter: "W" },
  doc: { bg: "#2B579A", letter: "W" },
};

function FileBadge({ name }: { name: string }) {
  const t = FILE_TYPES[name.split(".").pop()?.toLowerCase() ?? ""] ?? {
    bg: "#8A8F98",
    letter: "F",
  };
  return (
    <span
      aria-hidden
      className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-[5px] shadow-sm"
      style={{ backgroundColor: t.bg }}
    >
      <span className="text-[10px] leading-none font-bold text-white">
        {t.letter}
      </span>
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<
    string,
    { label: string; cls: string; icon: React.ReactNode }
  > = {
    parsed: {
      label: "已解析",
      cls: "font-medium text-success",
      icon: <CircleCheck className="h-3 w-3" />,
    },
    parsing: {
      label: "解析中",
      cls: "text-info",
      icon: <Loader2 className="h-3 w-3 animate-spin" />,
    },
    pending: {
      label: "排队中",
      cls: "text-info",
      icon: <Loader2 className="h-3 w-3 animate-spin" />,
    },
    failed: {
      label: "解析失败",
      cls: "text-destructive",
      icon: <CircleX className="h-3 w-3" />,
    },
    needs_review: {
      label: "待复核",
      cls: "font-medium text-amber-600",
      icon: <ListChecks className="h-3 w-3" />,
    },
  };
  const it = map[status] ?? {
    label: "未解析",
    cls: "text-muted-foreground",
    icon: <CircleDashed className="h-3 w-3" />,
  };
  return (
    <span className={cn("inline-flex items-center gap-1 text-xs", it.cls)}>
      {it.icon}
      {it.label}
    </span>
  );
}

function fmtSize(n: number): string {
  if (n >= 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  if (n >= 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${n} B`;
}

export function LibraryView() {
  const router = useRouter();
  const foldersQ = useLibraryFolders();
  const folders = useMemo(() => foldersQ.data?.items ?? [], [foldersQ.data]);
  const tree = useMemo(() => buildFolderTree(folders), [folders]);

  const [sel, setSel] = useState<string>(ROOT_ID);
  const [expanded, setExpanded] = useState<Set<string>>(new Set([ROOT_ID]));
  const [q, setQ] = useState("");
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [notice, setNotice] = useState<{
    kind: "ok" | "err";
    text: string;
  } | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [staged, setStaged] = useState<File[]>([]);
  const [folderDlg, setFolderDlg] = useState<{
    mode: "create" | "rename";
    id?: string;
    value: string;
  } | null>(null);
  const [moveFile, setMoveFile] = useState<CpaLibraryFile | null>(null);
  const [itemsFor, setItemsFor] = useState<CpaLibraryFile | null>(null);
  const filesInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  const filesQ = useLibraryFiles(sel === ROOT_ID ? null : sel);
  const muts = useLibraryMutations();
  const itemsQ = useQuery({
    queryKey: ["cpa", "library-items", itemsFor?.id],
    queryFn: () => libraryApi.fileItems(itemsFor!.id),
    enabled: !!itemsFor,
  });

  // flash 定时器句柄: 新通知先清旧定时器（防堆叠提前熄灭），卸载兜底清理
  const flashTimerRef = useRef<number | null>(null);
  const flash = (kind: "ok" | "err", text: string) => {
    if (flashTimerRef.current !== null)
      window.clearTimeout(flashTimerRef.current);
    setNotice({ kind, text });
    flashTimerRef.current = window.setTimeout(() => setNotice(null), 3500);
  };

  useEffect(() => {
    folderInputRef.current?.setAttribute("webkitdirectory", "");
  }, []);

  useEffect(
    () => () => {
      if (flashTimerRef.current !== null)
        window.clearTimeout(flashTimerRef.current);
    },
    [],
  );

  // Esc 关闭分项清单抽屉（镜像 TracebackDrawer 的 window keydown 写法）
  useEffect(() => {
    if (!itemsFor) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setItemsFor(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [itemsFor]);

  const files = (filesQ.data?.items ?? []).filter((f) =>
    q ? f.file_name.toLowerCase().includes(q.toLowerCase()) : true,
  );
  const analyzed = files.filter(
    (f) => checked.has(f.id) && f.parse_status !== "parsed",
  );

  const crumbs = pathOf(folders, sel);

  const toggleExpand = (id: string) =>
    setExpanded((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  const submitFolderDlg = async () => {
    if (!folderDlg?.value.trim()) return;
    try {
      if (folderDlg.mode === "create") {
        await muts.createFolder.mutateAsync({
          name: folderDlg.value.trim(),
          parentId: sel === ROOT_ID ? null : sel,
        });
      } else if (folderDlg.id) {
        await muts.updateFolder.mutateAsync({
          id: folderDlg.id,
          patch: { name: folderDlg.value.trim() },
        });
      }
      setFolderDlg(null);
      flash("ok", "文件夹已保存");
    } catch (e) {
      flash("err", `保存失败：${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const doUpload = async () => {
    if (!staged.length) return;
    try {
      const res = await muts.uploadFiles.mutateAsync({
        folderId: sel === ROOT_ID ? null : sel,
        files: staged,
      });
      const reused = res.items.filter((i) => i.reused).length;
      const failed = res.items.filter((i) => i.error);
      setStaged([]);
      setUploadOpen(false);
      flash(
        failed.length ? "err" : "ok",
        failed.length
          ? `${failed.length} 个文件失败（${failed[0]!.error}），其余已上传`
          : `已上传 ${res.items.length} 个文件（复用已有副本 ${reused} 个）`,
      );
    } catch (e) {
      flash("err", `上传失败：${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const doAnalyzeChecked = async () => {
    if (!analyzed.length) return;
    try {
      for (const f of analyzed) await muts.analyzeFile.mutateAsync(f.id);
      setChecked(new Set());
      flash(
        "ok",
        `已加入解析队列 ${analyzed.length} 个文件（下一轮解析自动拾取）`,
      );
    } catch (e) {
      flash(
        "err",
        `加入解析失败：${e instanceof Error ? e.message : String(e)}`,
      );
    }
  };

  const renderTree = (nodes: FolderNode[], depth: number): React.ReactNode =>
    nodes.map((n) => {
      const isOpen = expanded.has(n.id);
      const selected = sel === n.id;
      const hasChildren = n.children.length > 0;
      return (
        <div key={n.id} className="relative">
          {depth > 0 && (
            <span
              className="bg-border absolute top-0 bottom-0 w-px"
              style={{ left: depth * 12 - 2 }}
              aria-hidden
            />
          )}
          <div
            role="treeitem"
            aria-selected={selected}
            aria-expanded={hasChildren ? isOpen : undefined}
            tabIndex={0}
            className={cn(
              "group focus-visible:ring-ring/50 relative flex h-6 w-full cursor-pointer items-center gap-1 rounded-md pr-1 text-xs transition-colors outline-none select-none focus-visible:ring-2",
              selected
                ? "bg-accent text-accent-foreground font-medium"
                : "text-foreground/90 hover:bg-muted/70",
            )}
            style={{ paddingLeft: depth * 12 + 4 }}
            onClick={() => {
              setSel(n.id);
              if (hasChildren) toggleExpand(n.id);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                setSel(n.id);
                if (hasChildren) toggleExpand(n.id);
              }
            }}
          >
            {hasChildren ? (
              <ChevronRight
                className={cn(
                  "text-muted-foreground h-3 w-3 shrink-0 transition-transform duration-150",
                  isOpen && "rotate-90",
                )}
                onClick={(e) => {
                  // 仅展开/收起，不改变选中——键盘路径走行的 Enter/Space（同触发行点击+展开）
                  e.stopPropagation();
                  toggleExpand(n.id);
                }}
              />
            ) : (
              <span className="w-3 shrink-0" />
            )}
            <span className="truncate">{n.name}</span>
            <span className="ml-auto opacity-0 transition-opacity group-hover:opacity-100">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <span
                    className="hover:bg-muted rounded p-0.5"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <MoreHorizontal className="h-3.5 w-3.5" />
                  </span>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start">
                  <DropdownMenuItem
                    onClick={() => setFolderDlg({ mode: "create", value: "" })}
                  >
                    <FolderPlus className="mr-2 h-4 w-4" /> 添加子文件夹
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onClick={() =>
                      setFolderDlg({ mode: "rename", id: n.id, value: n.name })
                    }
                  >
                    <Pencil className="mr-2 h-4 w-4" /> 重命名
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    className="text-destructive"
                    onClick={async () => {
                      try {
                        await muts.deleteFolder.mutateAsync(n.id);
                        if (sel === n.id) setSel(ROOT_ID);
                        flash("ok", "文件夹已删除");
                      } catch (e) {
                        flash(
                          "err",
                          `删除失败：${e instanceof Error ? e.message : String(e)}`,
                        );
                      }
                    }}
                  >
                    <Trash2 className="mr-2 h-4 w-4" /> 删除
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </span>
          </div>
          {isOpen && hasChildren && (
            <div className="relative">{renderTree(n.children, depth + 1)}</div>
          )}
        </div>
      );
    });

  return (
    <div className="flex h-full flex-col gap-3 px-4 pt-3 pb-4">
      {/* 顶栏 */}
      <div className="flex items-center gap-3">
        <span className="flex-1" />
        <Button
          variant="outline"
          size="sm"
          onClick={() => router.push("/contract-price/tasks")}
        >
          解析队列 <ArrowRight className="ml-1 h-3.5 w-3.5" />
        </Button>
      </div>

      {notice && (
        <div
          className={cn(
            "rounded-md border px-3 py-2 text-sm",
            notice.kind === "ok"
              ? "border-success/30 bg-success/10 text-success"
              : "border-destructive/30 bg-destructive/10 text-destructive",
          )}
        >
          {notice.text}
        </div>
      )}

      {/* 面包屑 */}
      <div className="flex items-center gap-0.5 px-1 py-1 text-sm">
        {crumbs.map((seg, i) => (
          <span key={seg.id} className="flex items-center gap-0.5">
            {i > 0 && <span className="text-muted-foreground px-0.5">/</span>}
            <button
              className={cn(
                "hover:bg-muted hover:text-foreground rounded px-1 py-0.5 transition-colors",
                i === crumbs.length - 1 && "text-foreground font-medium",
              )}
              onClick={() => setSel(seg.id)}
            >
              {seg.name}
            </button>
          </span>
        ))}
      </div>

      {/* 主容器：pane 头 + 树 + 列表 */}
      <div className="flex min-h-[460px] flex-1 flex-col overflow-hidden rounded-lg border">
        <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2">
          <span className="text-sm font-medium">合同文件</span>
          <span className="text-muted-foreground text-xs">
            归档库 · 上传不自动解析
          </span>
          <span className="flex-1" />
          <Input
            placeholder="搜索文件名"
            className="h-8 w-44"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <Button
            variant="outline"
            size="sm"
            onClick={() => filesInputRef.current?.click()}
          >
            <Upload className="mr-1 h-3.5 w-3.5" /> 上传
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => folderInputRef.current?.click()}
          >
            <FolderPlus className="mr-1 h-3.5 w-3.5" /> 上传文件夹
          </Button>
          <Button
            size="sm"
            disabled={!analyzed.length}
            onClick={doAnalyzeChecked}
          >
            {muts.analyzeFile.isPending ? (
              <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
            ) : (
              <Zap className="mr-1 h-3.5 w-3.5" />
            )}
            加入解析{analyzed.length ? ` (${analyzed.length})` : ""}
          </Button>
          <input
            ref={filesInputRef}
            type="file"
            multiple
            accept=".pdf,.docx"
            className="hidden"
            onChange={(e) => {
              setStaged([...(e.target.files ?? [])]);
              setUploadOpen(true);
              e.target.value = "";
            }}
          />
          <input
            ref={folderInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => {
              setStaged([...(e.target.files ?? [])]);
              setUploadOpen(true);
              e.target.value = "";
            }}
          />
        </div>
        <div className="flex min-h-0 flex-1">
          <nav
            aria-label="文件夹树"
            className="bg-muted/20 w-44 shrink-0 overflow-auto border-r p-1 text-xs"
          >
            {/* 虚拟根「文件库」 */}
            <div
              role="treeitem"
              aria-selected={sel === ROOT_ID}
              aria-expanded
              tabIndex={0}
              className={cn(
                "group focus-visible:ring-ring/50 flex h-6 w-full cursor-pointer items-center gap-1 rounded-md px-1 text-xs outline-none select-none focus-visible:ring-2",
                sel === ROOT_ID
                  ? "bg-accent text-accent-foreground font-medium"
                  : "text-foreground/90 hover:bg-muted/70",
              )}
              onClick={() => setSel(ROOT_ID)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  setSel(ROOT_ID);
                }
              }}
            >
              <ChevronRight className="text-muted-foreground h-3 w-3 shrink-0 rotate-90" />
              <span>文件库</span>
              <span className="ml-auto opacity-0 transition-opacity group-hover:opacity-100">
                <FolderPlus
                  className="h-3.5 w-3.5 cursor-pointer"
                  onClick={(e) => {
                    e.stopPropagation();
                    setFolderDlg({ mode: "create", value: "" });
                  }}
                />
              </span>
            </div>
            {foldersQ.isError ? (
              <p className="text-destructive px-1 py-1">
                文件夹加载失败：{String(foldersQ.error)}
              </p>
            ) : foldersQ.isLoading ? (
              <div className="text-muted-foreground flex items-center gap-2 py-1">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> 加载中…
              </div>
            ) : (
              renderTree(tree, 1)
            )}
          </nav>
          <div className="min-w-0 flex-1 overflow-auto">
            {filesQ.isError ? (
              <p className="text-destructive p-4 text-sm">
                文件加载失败：{String(filesQ.error)}
              </p>
            ) : filesQ.isLoading ? (
              <div className="text-muted-foreground flex items-center gap-2 p-4 text-sm">
                <Loader2 className="h-4 w-4 animate-spin" /> 加载中…
              </div>
            ) : files.length === 0 ? (
              <div className="text-muted-foreground p-8 text-center text-sm">
                {q && (filesQ.data?.items.length ?? 0) > 0
                  ? `没有匹配「${q}」的文件`
                  : "此文件夹还没有合同文件。上传后归档于此；需要解析时勾选文件点「加入解析」。"}
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-muted/50 text-muted-foreground border-b text-left text-xs">
                    <th className="w-8 px-2 py-2">
                      <input
                        type="checkbox"
                        aria-label="全选"
                        className="accent-primary h-3.5 w-3.5 cursor-pointer"
                        checked={
                          files.every((f) => checked.has(f.id)) &&
                          files.length > 0
                        }
                        onChange={(e) =>
                          setChecked(
                            e.target.checked
                              ? new Set(files.map((f) => f.id))
                              : new Set(),
                          )
                        }
                      />
                    </th>
                    <th className="px-2 py-2">文件名</th>
                    <th className="w-10 px-2 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {files.map((f) => (
                    <tr
                      key={f.id}
                      className="hover:bg-muted/50 border-b last:border-b-0"
                    >
                      <td className="px-2 py-2">
                        <input
                          type="checkbox"
                          aria-label={`选择 ${f.file_name}`}
                          className="accent-primary h-3.5 w-3.5 cursor-pointer"
                          checked={checked.has(f.id)}
                          onChange={(e) => {
                            const s = new Set(checked);
                            if (e.target.checked) s.add(f.id);
                            else s.delete(f.id);
                            setChecked(s);
                          }}
                        />
                      </td>
                      <td className="min-w-0 px-2 py-2">
                        <div className="flex items-center gap-2.5">
                          <FileBadge name={f.file_name} />
                          <div className="min-w-0">
                            <div className="truncate text-sm">
                              {f.file_name}
                            </div>
                            <div className="text-muted-foreground flex items-center gap-1.5 truncate text-xs">
                              <StatusBadge status={f.parse_status} />
                              <span className="uppercase">{f.file_type}</span>
                              <span>·</span>
                              <span>{fmtSize(f.file_size)}</span>
                              <span>·</span>
                              <span>
                                {new Date(f.uploaded_at).toLocaleDateString(
                                  "zh-CN",
                                )}
                              </span>
                            </div>
                          </div>
                        </div>
                      </td>
                      <td className="w-10 px-2 py-2 text-right">
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-7 w-7 p-0"
                            >
                              <MoreHorizontal className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem asChild>
                              <a
                                href={libraryApi.fileContentUrl(f.id)}
                                target="_blank"
                                rel="noreferrer"
                              >
                                <Eye className="mr-2 h-4 w-4" /> 在线查阅
                              </a>
                            </DropdownMenuItem>
                            {f.parse_status === "parsed" && (
                              <DropdownMenuItem onClick={() => setItemsFor(f)}>
                                <ListChecks className="mr-2 h-4 w-4" />{" "}
                                查看分项清单
                              </DropdownMenuItem>
                            )}
                            {f.parse_status !== "parsed" && (
                              <DropdownMenuItem
                                onClick={async () => {
                                  try {
                                    const r =
                                      await muts.analyzeFile.mutateAsync(f.id);
                                    flash("ok", r.message);
                                  } catch (e) {
                                    flash(
                                      "err",
                                      `加入解析失败：${e instanceof Error ? e.message : String(e)}`,
                                    );
                                  }
                                }}
                              >
                                <Zap className="mr-2 h-4 w-4" /> 加入解析
                              </DropdownMenuItem>
                            )}
                            <DropdownMenuItem asChild>
                              <a
                                href={libraryApi.fileContentUrl(f.id)}
                                download
                              >
                                <Download className="mr-2 h-4 w-4" /> 下载
                              </a>
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => setMoveFile(f)}>
                              <FolderInput className="mr-2 h-4 w-4" /> 移动到…
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              className="text-destructive"
                              onClick={async () => {
                                try {
                                  await muts.deleteFile.mutateAsync(f.id);
                                  setChecked((s) => {
                                    const n = new Set(s);
                                    n.delete(f.id);
                                    return n;
                                  });
                                  flash("ok", "文件已删除");
                                } catch (e) {
                                  flash(
                                    "err",
                                    `删除失败：${e instanceof Error ? e.message : String(e)}`,
                                  );
                                }
                              }}
                            >
                              <Trash2 className="mr-2 h-4 w-4" /> 删除
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>

      {/* 统计底栏 */}
      <div className="bg-muted/30 flex flex-wrap items-center gap-4 rounded-md border px-3 py-2 text-sm">
        <span>
          共 <b>{filesQ.data?.items.length ?? 0}</b>（当前文件夹）
        </span>
        <span>
          已解析{" "}
          <b>
            {
              (filesQ.data?.items ?? []).filter(
                (f) => f.parse_status === "parsed",
              ).length
            }
          </b>
        </span>
        <span className="text-muted-foreground text-xs">
          上传不自动解析 · 勾选文件后点「加入解析」 · 与解析管线解耦
        </span>
      </div>

      {/* 上传确认对话框 */}
      <Dialog open={uploadOpen} onOpenChange={setUploadOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>上传合同文件</DialogTitle>
          </DialogHeader>
          {staged.length === 0 ? (
            <button
              className="text-muted-foreground hover:border-primary hover:text-primary rounded-lg border border-dashed p-6 text-center text-sm"
              onClick={() => filesInputRef.current?.click()}
            >
              点击选择文件（仅接受 .pdf / .docx）
            </button>
          ) : (
            <div className="max-h-56 space-y-1.5 overflow-auto">
              {staged.map((f) => {
                const rel =
                  (f as File & { webkitRelativePath?: string })
                    .webkitRelativePath || f.name;
                return (
                  <div
                    key={rel}
                    className="flex items-center gap-2 rounded-md border px-2 py-1.5 text-sm"
                  >
                    <FileBadge name={f.name} />
                    <span className="min-w-0 flex-1 truncate">{rel}</span>
                    <span className="text-muted-foreground text-xs">
                      {fmtSize(f.size)}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
          <p className="text-muted-foreground text-xs">
            文件夹上传按相对路径自动建子文件夹；同文件夹相同内容的文件复用已上传副本；本库上传不会自动触发解析。
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setUploadOpen(false)}>
              取消
            </Button>
            <Button
              onClick={doUpload}
              disabled={!staged.length || muts.uploadFiles.isPending}
            >
              {muts.uploadFiles.isPending
                ? "上传中…"
                : `开始上传 (${staged.length})`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 新建/重命名文件夹 */}
      <Dialog open={!!folderDlg} onOpenChange={(v) => !v && setFolderDlg(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>
              {folderDlg?.mode === "create" ? "新建文件夹" : "重命名文件夹"}
            </DialogTitle>
          </DialogHeader>
          <Input
            autoFocus
            placeholder="文件夹名"
            value={folderDlg?.value ?? ""}
            onChange={(e) =>
              setFolderDlg((d) => (d ? { ...d, value: e.target.value } : d))
            }
            onKeyDown={(e) => e.key === "Enter" && submitFolderDlg()}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setFolderDlg(null)}>
              取消
            </Button>
            <Button
              onClick={submitFolderDlg}
              disabled={!folderDlg?.value.trim()}
            >
              保存
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 移动到… */}
      <Dialog open={!!moveFile} onOpenChange={(v) => !v && setMoveFile(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>移动「{moveFile?.file_name}」到…</DialogTitle>
          </DialogHeader>
          <select
            className="bg-background h-9 w-full rounded-md border px-2 text-sm"
            defaultValue=""
            onChange={async (e) => {
              if (!moveFile) return;
              const target = e.target.value === "" ? null : e.target.value;
              try {
                await muts.moveFile.mutateAsync({
                  id: moveFile.id,
                  folderId: target,
                });
                setMoveFile(null);
                flash("ok", "文件已移动");
              } catch (err) {
                flash(
                  "err",
                  `移动失败：${err instanceof Error ? err.message : String(err)}`,
                );
              }
            }}
          >
            <option value="">文件库（根）</option>
            {folders.map((f) => (
              <option key={f.id} value={f.id}>
                {pathOf(folders, f.id)
                  .slice(1)
                  .map((s) => s.name)
                  .join(" / ")}
              </option>
            ))}
          </select>
        </DialogContent>
      </Dialog>

      {/* 分项清单抽屉 */}
      {itemsFor && (
        <div
          className="fixed inset-0 z-50 flex justify-end bg-black/45"
          role="dialog"
          aria-modal="true"
          aria-label="分项清单"
          onClick={() => setItemsFor(null)}
        >
          <aside
            className="bg-card flex h-full w-full max-w-xl flex-col border-l shadow-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-2 border-b px-4 py-3">
              <h3 className="min-w-0 flex-1 truncate text-base font-semibold">
                {itemsFor.file_name} · 分项清单
              </h3>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setItemsFor(null)}
              >
                ✕
              </Button>
            </div>
            <div className="min-h-0 flex-1 overflow-auto p-4">
              {itemsQ.isLoading ? (
                <div className="text-muted-foreground flex items-center gap-2 text-sm">
                  <Loader2 className="h-4 w-4 animate-spin" /> 加载中…
                </div>
              ) : itemsQ.isError ? (
                <p className="text-destructive text-sm">
                  {String(itemsQ.error)}
                </p>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-muted/50 text-muted-foreground border-b text-left text-xs">
                      <th className="px-2 py-2">货物名称</th>
                      <th className="px-2 py-2">规格型号</th>
                      <th className="px-2 py-2 text-right">数量</th>
                      <th className="px-2 py-2">单位</th>
                      <th className="px-2 py-2 text-right">含税单价</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(itemsQ.data?.items ?? []).map((it) => (
                      <tr key={it.id} className="border-b last:border-b-0">
                        <td className="px-2 py-2 font-medium">
                          {it.goods_name}
                        </td>
                        <td className="px-2 py-2 text-xs">
                          {it.spec_model ?? "—"}
                        </td>
                        <td className="px-2 py-2 text-right tabular-nums">
                          {it.quantity ?? "—"}
                        </td>
                        <td className="px-2 py-2">{it.unit ?? "—"}</td>
                        <td className="px-2 py-2 text-right font-semibold tabular-nums">
                          {it.unit_price != null
                            ? `¥${Number(it.unit_price).toLocaleString("zh-CN", { minimumFractionDigits: 2 })}`
                            : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
            <div className="flex justify-end gap-2 border-t px-4 py-3">
              <Button variant="outline" onClick={() => setItemsFor(null)}>
                关闭
              </Button>
              <Button onClick={() => router.push("/contract-price/items")}>
                去分项校验 <ArrowRight className="ml-1 h-3.5 w-3.5" />
              </Button>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
