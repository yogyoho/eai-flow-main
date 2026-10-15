"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  ArrowLeftToLine,
  ArrowRightToLine,
  Ban,
  ChevronRight,
  CircleCheck,
  CircleDashed,
  CircleX,
  ClipboardCheck,
  Clock,
  Database,
  Download,
  Eye,
  FilePlus2,
  FolderPlus,
  GripVerticalIcon,
  History,
  Loader2,
  MoreHorizontal,
  Pencil,
  Play,
  RefreshCw,
  ShieldAlert,
  Trash2,
  Upload,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { artifactMarkdownPlugins } from "@/components/workspace/artifacts/markdown-preview-plugins";
import { SafeStreamdown } from "@/core/streamdown/components";
import { cn } from "@/lib/utils";

import {
  createFolder,
  deleteFolder,
  deleteTask,
  fetchDeliverablePreview,
  listFolders,
  listRagKbs,
  listTasks,
  patchFolder,
  translateTask,
  uploadAssets,
} from "../api";
import type { TltFolder, TltTask } from "../types";

import { FileIcon } from "./FileIcon";
import { WindowsFolder, WindowsFolderOpen } from "./FolderIcons";
import { SourcePreview } from "./SourcePreview";
import { UploadDialog } from "./UploadDialog";

const PAGE_SIZE = 50;
const POLL_MS = 10_000;

type FolderId = string | null; // null = 根

interface FolderNode extends TltFolder {
  children: FolderNode[];
}

function buildTree(folders: TltFolder[]): FolderNode[] {
  const nodes = new Map<string, FolderNode>(
    folders.map((f) => [f.id, { ...f, children: [] }]),
  );
  const roots: FolderNode[] = [];
  for (const node of nodes.values()) {
    if (node.parent_id && nodes.has(node.parent_id)) {
      nodes.get(node.parent_id)!.children.push(node);
    } else {
      roots.push(node);
    }
  }
  return roots;
}

function fmtSize(bytes: number | null | undefined): string {
  if (bytes == null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? "—"
    : d.toLocaleString("zh-CN", { hour12: false });
}

/** 状态 → 用户语徽章（文案红线映射表）。 */
function StateBadge({ state, progress }: { state: string; progress?: number }) {
  // 图标用 lucide 线性件（文案红线：禁 emoji/unicode 符号）
  const map: Record<
    string,
    { label: string; cls: string; icon: React.ReactNode }
  > = {
    stored: {
      label: "未翻译",
      cls: "border-dashed text-muted-foreground",
      icon: <CircleDashed className="h-3 w-3" />,
    },
    pending: {
      label: "排队中",
      cls: "text-muted-foreground",
      icon: <Clock className="h-3 w-3" />,
    },
    running: {
      label: `翻译中${progress ? ` ${progress}%` : ""}`,
      cls: "text-info",
      icon: <Loader2 className="h-3 w-3 animate-spin" />,
    },
    check_failed: {
      label: "机检未过",
      cls: "text-amber-600",
      icon: <ShieldAlert className="h-3 w-3" />,
    },
    retrying: {
      label: "重试中",
      cls: "text-amber-600",
      icon: <RefreshCw className="h-3 w-3 animate-spin" />,
    },
    exceeded: {
      label: "待复核",
      cls: "text-amber-600 font-medium",
      icon: <ClipboardCheck className="h-3 w-3" />,
    },
    indexed: {
      label: "入库中",
      cls: "text-info",
      icon: <Database className="h-3 w-3" />,
    },
    delivered: {
      label: "已交付",
      cls: "text-success font-medium",
      icon: <CircleCheck className="h-3 w-3" />,
    },
    failed: {
      label: "失败",
      cls: "text-destructive",
      icon: <CircleX className="h-3 w-3" />,
    },
    archived: {
      label: "已归档",
      cls: "text-muted-foreground",
      icon: <Archive className="h-3 w-3" />,
    },
    cancelled: {
      label: "已取消",
      cls: "text-muted-foreground",
      icon: <Ban className="h-3 w-3" />,
    },
    superseded: {
      label: "已替代",
      cls: "text-muted-foreground",
      icon: <History className="h-3 w-3" />,
    },
  };
  const it = map[state] ?? { label: state, cls: "", icon: null };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs whitespace-nowrap",
        it.cls,
      )}
    >
      {it.icon}
      {it.label}
    </span>
  );
}

export function AssetLibrary() {
  // 浏览器标签页标题（client 组件不可导出 metadata，用 effect 设置）
  useEffect(() => {
    document.title = "文档资产库 EN/FR 文档 · 中文译本对照管理";
  }, []);
  const qc = useQueryClient();
  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["tlt-tasks"] });
    void qc.invalidateQueries({ queryKey: ["tlt-folders"] });
  };

  // 双栏导航（镜像模型：右侧树为只读投影，可独立导航）
  const [lFolder, setLFolder] = useState<FolderId>("root");
  const [rFolder, setRFolder] = useState<FolderId>("root");
  const [lPage, setLPage] = useState(1);
  const [q, setQ] = useState("");
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [paneWidth, setPaneWidth] = useState(50); // %
  const [collapsed, setCollapsed] = useState<"none" | "right" | "left">("none");
  const [lTreeW, setLTreeW] = useState(150);
  const [rTreeW, setRTreeW] = useState(150);
  /** 树↔列表 拖拽分隔（每侧独立，96-280px 夹取）。 */
  const startTreeDrag = (side: "L" | "R") => (e: React.MouseEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const startW = side === "L" ? lTreeW : rTreeW;
    const move = (ev: MouseEvent) => {
      const w = Math.min(280, Math.max(96, startW + (ev.clientX - startX)));
      if (side === "L") {
        setLTreeW(w);
      } else {
        setRTreeW(w);
      }
    };
    const up = () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
      document.body.style.cursor = "";
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    document.body.style.cursor = "col-resize";
  };
  const [expanded, setExpanded] = useState<Set<string>>(new Set(["root"]));
  const [notice, setNotice] = useState<{
    kind: "ok" | "err";
    text: string;
  } | null>(null);
  const [previewTask, setPreviewTask] = useState<TltTask | null>(null);
  const [previewMd, setPreviewMd] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [folderDialog, setFolderDialog] = useState<{
    mode: "create" | "rename";
    id?: string;
    parent?: FolderId;
    value: string;
  } | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const splitRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  // ── RAG 库选择（上传目标 + 列表筛选）──
  const ragKbsQ = useQuery({ queryKey: ["tlt-rag-kbs"], queryFn: listRagKbs });
  const ragKbs = useMemo(() => ragKbsQ.data ?? [], [ragKbsQ.data]);
  // 记忆上次目标库；无记忆则用设置页默认库（SSR 守卫同 SettingsView）
  const [uploadKbId, setUploadKbId] = useState<string>(() => {
    if (typeof window === "undefined") return "";
    const last = window.localStorage.getItem("tlt_last_kb_id");
    if (last) return last;
    return window.localStorage.getItem("tlt_default_kb_id") ?? "";
  });
  const [kbFilter, setKbFilter] = useState<string>("all");

  // 回落：选项加载后选中值已不在库列表 → 默认库 → 唯一库 → ""（"" 时后端 400 引导，不静默进错库）
  useEffect(() => {
    if (ragKbsQ.isLoading || ragKbs.length === 0) return;
    if (ragKbs.some((k) => k.id === uploadKbId)) return;
    const only = ragKbs.length === 1 ? ragKbs[0] : undefined;
    const fallback =
      ragKbs.find(
        (k) => k.id === window.localStorage.getItem("tlt_default_kb_id"),
      )?.id ??
      only?.id ??
      "";
    setUploadKbId(fallback);
  }, [ragKbsQ.isLoading, ragKbs, uploadKbId]);

  const foldersQ = useQuery({
    queryKey: ["tlt-folders"],
    queryFn: listFolders,
  });
  const tasksL = useQuery({
    queryKey: ["tlt-tasks", "L", lFolder, lPage, q, kbFilter],
    queryFn: () =>
      listTasks({
        folder_id: lFolder,
        page: lPage,
        page_size: PAGE_SIZE,
        q: q || undefined,
        ...(kbFilter !== "all" ? { kb_id: kbFilter } : {}),
      }),
    refetchInterval: POLL_MS,
  });
  const tasksR = useQuery({
    queryKey: ["tlt-tasks", "R", rFolder],
    queryFn: () => listTasks({ folder_id: rFolder, page_size: 200 }),
    refetchInterval: POLL_MS,
  });
  const reviewQ = useQuery({
    queryKey: ["tlt-tasks", "exceeded-count"],
    queryFn: () => listTasks({ state: "exceeded", page_size: 1 }),
    refetchInterval: 30_000,
  });

  const folders = useMemo(() => foldersQ.data ?? [], [foldersQ.data]);
  const tree = useMemo(() => buildTree(folders), [folders]);
  const lTasks = tasksL.data?.items ?? [];
  const rTasks = (tasksR.data?.items ?? []).filter(
    (t) => t.state !== "stored" && t.state !== "archived",
  );
  const translatable = lTasks.filter(
    (t) => checked.has(t.id) && (t.state === "stored" || t.state === "failed"),
  );

  const flash = (kind: "ok" | "err", text: string) => {
    setNotice({ kind, text });
    window.setTimeout(() => setNotice(null), 3500);
  };

  // ── 分隔条拖拽（监听挂 window：仅客户端，useEffect 内）──
  const onSplitDown = () => {
    dragging.current = true;
    document.body.style.cursor = "col-resize";
  };
  useEffect(() => {
    const move = (e: MouseEvent) => {
      if (!dragging.current || !splitRef.current) return;
      const r = splitRef.current.getBoundingClientRect();
      setPaneWidth(
        Math.min(75, Math.max(25, ((e.clientX - r.left) / r.width) * 100)),
      );
    };
    const up = () => {
      dragging.current = false;
      document.body.style.cursor = "";
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
  }, []);

  // ── 动作 ──
  /** 上传对话框回调：存原件建 stored 任务；勾选自动翻译时逐个入队 pending。 */
  const handleUpload = async (files: File[], autoTranslate: boolean) => {
    try {
      const folderId = lFolder === "root" ? null : lFolder;
      const res = await uploadAssets(folderId, files, uploadKbId || null);
      // 请求级成功才记忆本次目标库（失败路径不写，保留上一次成功值）
      if (uploadKbId) window.localStorage.setItem("tlt_last_kb_id", uploadKbId);
      if (autoTranslate) {
        for (const item of res) {
          if (!item.reused) await translateTask(item.task_id);
        }
      }
      invalidate();
      const created = res.filter((r) => !r.reused).length;
      flash(
        "ok",
        `已上传 ${res.length} 个文件（新建翻译任务 ${created} 个${autoTranslate && created ? "，已入队" : ""}）`,
      );
      return { total: files.length, failed: [] as File[] };
    } catch (e) {
      // 服务端错误上抛给对话框显示（不再未处理崩溃）；全部文件留在选择列表可重试
      return {
        total: files.length,
        failed: files,
        message: e instanceof Error ? e.message : String(e),
      };
    }
  };

  const doTranslateChecked = async () => {
    if (!translatable.length) return;
    try {
      for (const t of translatable) await translateTask(t.id);
      invalidate();
      setChecked(new Set());
      flash("ok", `已提交 ${translatable.length} 个翻译任务`);
    } catch (e) {
      flash("err", `提交失败：${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const doDelete = async (t: TltTask) => {
    try {
      await deleteTask(t.id);
      invalidate();
      const s = new Set(checked);
      s.delete(t.id);
      setChecked(s);
      flash("ok", "已移出资产库（可恢复）");
    } catch (e) {
      flash("err", `删除失败：${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const openPreview = (t: TltTask) => {
    setPreviewTask(t);
    setPreviewMd(null);
    setPreviewLoading(true);
    void fetchDeliverablePreview(t.id)
      .then(setPreviewMd)
      .catch((e) =>
        flash("err", `预览失败：${e instanceof Error ? e.message : String(e)}`),
      )
      .finally(() => setPreviewLoading(false));
  };

  const submitFolderDialog = async () => {
    if (!folderDialog) return;
    try {
      if (folderDialog.mode === "create") {
        await createFolder(
          folderDialog.value.trim(),
          folderDialog.parent ?? null,
        );
      } else if (folderDialog.id) {
        await patchFolder(folderDialog.id, { name: folderDialog.value.trim() });
      }
      setFolderDialog(null);
      invalidate();
      flash("ok", "文件夹已保存");
    } catch (e) {
      flash("err", `保存失败：${e instanceof Error ? e.message : String(e)}`);
    }
  };

  // ── 树渲染（Explorer 风格：旋转箭头 + Windows 文件夹图标 + 缩进参考线）──
  const renderTree = (nodes: FolderNode[], depth: number, side: "L" | "R") =>
    nodes.map((n) => {
      const isOpen = expanded.has(n.id);
      const selected = (side === "L" ? lFolder : rFolder) === n.id;
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
            aria-expanded={hasChildren ? isOpen : undefined}
            aria-selected={selected}
            tabIndex={0}
            className={cn(
              "group relative flex h-6 w-full cursor-pointer items-center gap-1 rounded-md pr-1 text-xs transition-colors outline-none select-none",
              "focus-visible:ring-ring/50 focus-visible:ring-2",
              selected
                ? "bg-accent text-accent-foreground font-medium"
                : "text-foreground/90 hover:bg-muted/70",
            )}
            style={{ paddingLeft: depth * 12 + 4 }}
            onClick={() => {
              if (hasChildren) {
                setExpanded((s) => {
                  const next = new Set(s);
                  if (next.has(n.id)) {
                    next.delete(n.id);
                  } else {
                    next.add(n.id);
                  }
                  return next;
                });
              }
              if (side === "L") {
                setLFolder(n.id);
                setRFolder(n.id); // 镜像一致性：左导航驱动右栏同步
                setLPage(1);
              } else {
                setRFolder(n.id);
              }
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                (e.currentTarget as HTMLDivElement).click();
              }
            }}
          >
            {hasChildren ? (
              <ChevronRight
                className={cn(
                  "text-muted-foreground h-3 w-3 shrink-0 transition-transform duration-150",
                  isOpen && "rotate-90",
                )}
              />
            ) : (
              <span className="w-3 shrink-0" />
            )}
            {isOpen ? (
              <WindowsFolderOpen className="h-3.5 w-3.5 shrink-0 drop-shadow-sm" />
            ) : (
              <WindowsFolder className="h-3.5 w-3.5 shrink-0 drop-shadow-sm" />
            )}
            <span className="truncate">{n.name}</span>
            {side === "L" && (
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
                      onClick={(e) => {
                        e.stopPropagation();
                        setExpanded((s) => new Set(s).add(n.id));
                        setFolderDialog({
                          mode: "create",
                          parent: n.id,
                          value: "",
                        });
                      }}
                    >
                      <FolderPlus className="mr-2 h-4 w-4" />{" "}
                      {n.id === "root" ? "子文件夹" : "添加子文件夹"}
                    </DropdownMenuItem>
                    {n.id !== "root" && (
                      <>
                        <DropdownMenuItem
                          onClick={(e) => {
                            e.stopPropagation();
                            setFolderDialog({
                              mode: "rename",
                              id: n.id,
                              value: n.name,
                            });
                          }}
                        >
                          <Pencil className="mr-2 h-4 w-4" /> 重命名
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          className="text-destructive"
                          onClick={async (e) => {
                            e.stopPropagation();
                            try {
                              await deleteFolder(n.id);
                              invalidate();
                              if (lFolder === n.id) setLFolder("root");
                              if (rFolder === n.id) setRFolder("root");
                              flash("ok", "文件夹已删除");
                            } catch (err) {
                              flash(
                                "err",
                                `删除失败：${err instanceof Error ? err.message : String(err)}`,
                              );
                            }
                          }}
                        >
                          <Trash2 className="mr-2 h-4 w-4" /> 删除
                        </DropdownMenuItem>
                      </>
                    )}
                  </DropdownMenuContent>
                </DropdownMenu>
              </span>
            )}
          </div>
          {isOpen && hasChildren && (
            <div className="relative">
              {renderTree(n.children, depth + 1, side)}
            </div>
          )}
        </div>
      );
    });

  /** 当前文件夹的路径链（面包屑用）。 */
  const folderPath = (folderId: FolderId): { id: FolderId; name: string }[] => {
    if (folderId === "root" || !folderId)
      return [{ id: "root", name: "文件库" }];
    const byId = new Map(folders.map((f) => [f.id, f]));
    const chain: { id: FolderId; name: string }[] = [];
    let cur = byId.get(folderId);
    while (cur) {
      chain.unshift({ id: cur.id, name: cur.name });
      cur = cur.parent_id ? byId.get(cur.parent_id) : undefined;
    }
    return [{ id: "root", name: "文件库" }, ...chain];
  };

  const Crumbs = ({
    folderId,
    onPick,
  }: {
    folderId: FolderId;
    onPick: (id: FolderId) => void;
  }) => {
    const chain = folderPath(folderId);
    return (
      <div className="text-muted-foreground flex items-center gap-0.5 text-xs">
        {chain.map((seg, i) => (
          <span key={seg.id ?? "root"} className="flex items-center gap-0.5">
            {i > 0 && <span className="px-0.5">/</span>}
            <button
              className={cn(
                "hover:bg-muted hover:text-foreground rounded px-1 py-0.5 transition-colors",
                i === chain.length - 1 && "text-foreground font-medium",
              )}
              onClick={() => onPick(seg.id)}
            >
              {seg.name}
            </button>
          </span>
        ))}
      </div>
    );
  };

  const TreePane = ({ side, width }: { side: "L" | "R"; width: number }) => {
    // 虚拟根「文件库」：可选中（浏览根级文件）、可建子文件夹；不可重命名/删除
    const displayTree: FolderNode[] = [
      { id: "root", name: "文件库", parent_id: null, children: tree },
    ];
    return (
      <div
        className="bg-muted/20 flex shrink-0 flex-col overflow-auto border-r p-1 text-xs"
        style={{ width: `${width}px`, maxHeight: "inherit" }}
      >
        {foldersQ.isLoading ? (
          <SkeletonRow />
        ) : (
          renderTree(displayTree, 0, side)
        )}
      </div>
    );
  };

  const SkeletonRow = () => (
    <div className="flex items-center gap-2 py-1">
      <Loader2 className="text-muted-foreground h-3.5 w-3.5 animate-spin" />
      <span className="text-muted-foreground text-xs">加载中…</span>
    </div>
  );

  const OpsMenu = ({ t, side }: { t: TltTask; side: "L" | "R" }) => (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" className="h-7 w-7 p-0">
          <MoreHorizontal className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {side === "L" && (t.state === "stored" || t.state === "failed") && (
          <DropdownMenuItem
            onClick={() => {
              void translateTask(t.id)
                .then(() => {
                  invalidate();
                  flash("ok", "已加入翻译队列");
                })
                .catch((e) => flash("err", String(e)));
            }}
          >
            <Play className="mr-2 h-4 w-4" /> 翻译
          </DropdownMenuItem>
        )}
        <DropdownMenuItem asChild>
          <a href={`/api/extensions/translation/tasks/${t.id}/source`}>
            <Download className="mr-2 h-4 w-4" /> 下载原件
          </a>
        </DropdownMenuItem>
        {side === "R" && t.state === "delivered" && (
          <>
            <DropdownMenuItem onClick={() => openPreview(t)}>
              <Eye className="mr-2 h-4 w-4" /> 预览
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <a href={`/api/extensions/translation/tasks/${t.id}/deliverable`}>
                <Download className="mr-2 h-4 w-4" /> 下载译文
              </a>
            </DropdownMenuItem>
          </>
        )}
        <DropdownMenuItem
          className="text-destructive"
          onClick={() => doDelete(t)}
        >
          <Trash2 className="mr-2 h-4 w-4" /> 移出资产库
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );

  return (
    <div className="flex h-full flex-col gap-3 px-4 pt-0 pb-4">
      {/* 顶栏 */}
      <div className="flex items-center gap-3">
        {/* <h1 className="flex items-center gap-2 text-xl font-semibold">
          <Languages className="h-5 w-5" /> 文档资产库 EN/FR 文档 · 中文译本对照管理
        </h1> */}
        <span className="flex-1" />
        {reviewQ.data && reviewQ.data.total > 0 && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => flash("ok", "复核工作台建设中（OQ8）")}
          >
            待复核 {reviewQ.data.total} →
          </Button>
        )}
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

      {/* 路径面包屑（左侧主导航；点击层级=左右同步前往） */}
      <div className="flex items-center gap-2 px-3 py-1.5 text-sm">
        <span className="shrink-0 rounded-sm bg-sky-100 px-2 py-0.5 text-xs text-sky-700">
          文件路径：
        </span>
        <Crumbs
          folderId={lFolder}
          onPick={(id) => {
            setLFolder(id);
            setRFolder(id);
            setLPage(1);
          }}
        />
      </div>

      {/* 双栏 */}
      <div
        ref={splitRef}
        className="flex min-h-[460px] flex-1 overflow-hidden rounded-lg border"
      >
        {/* 左：原文区 */}
        <div
          className={cn(
            "flex min-w-0 flex-col",
            collapsed === "left" && "hidden",
          )}
          style={
            collapsed === "right" ? { flex: 1 } : { width: `${paneWidth}%` }
          }
        >
          <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2">
            <span className="text-sm font-medium">原文区</span>
            <span className="text-muted-foreground text-xs">EN/FR</span>
            <span className="flex-1" />
            <Input
              placeholder="搜索 文件名 / sha"
              className="h-8 w-44"
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setLPage(1);
              }}
            />
            <select
              className="bg-background h-8 rounded-md border px-2 text-sm"
              value={kbFilter}
              onChange={(e) => {
                setKbFilter(e.target.value);
                setLPage(1);
              }}
            >
              <option value="all">全部库</option>
              {ragKbs.map((k) => (
                <option key={k.id} value={k.id}>
                  {k.name}
                </option>
              ))}
            </select>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setUploadOpen(true)}
            >
              <Upload className="mr-1 h-3.5 w-3.5" /> 上传
            </Button>
            <Button
              size="sm"
              disabled={!translatable.length}
              onClick={doTranslateChecked}
            >
              {tasksL.isFetching ? (
                <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
              ) : (
                <Play className="mr-1 h-3.5 w-3.5" />
              )}
              翻译 ({translatable.length})
            </Button>
            {/* 左全宽切换：右区消失/复原（样式对齐列表头部 ghost 图标钮） */}
            <Button
              variant="ghost"
              size="sm"
              className="h-9 w-9 p-0"
              title={collapsed === "right" ? "复原双栏" : "左全宽"}
              onClick={() =>
                setCollapsed(collapsed === "right" ? "none" : "right")
              }
            >
              {collapsed === "right" ? (
                <ArrowLeftToLine className="h-4 w-4" />
              ) : (
                <ArrowRightToLine className="h-4 w-4" />
              )}
            </Button>
          </div>
          <div className="flex min-h-0 flex-1">
            <TreePane side="L" width={lTreeW} />
            <div
              className="hover:bg-muted w-1 shrink-0 cursor-col-resize bg-transparent"
              onMouseDown={startTreeDrag("L")}
            />
            <div className="min-w-0 flex-1 overflow-auto">
              {tasksL.isLoading ? (
                <div className="text-muted-foreground flex items-center gap-2 p-4 text-sm">
                  <Loader2 className="h-4 w-4 animate-spin" /> 加载中…
                </div>
              ) : lTasks.length === 0 ? (
                <div className="text-muted-foreground p-8 text-center text-sm">
                  此文件夹还没有文档。上传 EN/FR 文档后开始翻译。
                </div>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-muted/50 text-muted-foreground border-b text-left text-xs">
                      <th className="w-8 px-2 py-2">
                        <Checkbox
                          checked={
                            lTasks.every((t) => checked.has(t.id)) &&
                            lTasks.length > 0
                          }
                          onCheckedChange={(v) =>
                            setChecked(
                              v ? new Set(lTasks.map((t) => t.id)) : new Set(),
                            )
                          }
                          className="border-muted-foreground/40 hover:border-primary data-[state=checked]:border-primary data-[state=checked]:bg-primary h-3.5 w-3.5 rounded-[4px] shadow-none transition-all"
                        />
                      </th>
                      <th className="px-2 py-2">文件名</th>
                      <th className="w-10 px-2 py-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {lTasks.map((t) => (
                      <tr
                        key={t.id}
                        className="hover:bg-muted/50 border-b last:border-b-0"
                      >
                        <td className="px-2 py-2">
                          <Checkbox
                            checked={checked.has(t.id)}
                            onCheckedChange={(v) => {
                              const s = new Set(checked);
                              if (v) {
                                s.add(t.id);
                              } else {
                                s.delete(t.id);
                              }
                              setChecked(s);
                            }}
                            className="border-muted-foreground/40 hover:border-primary data-[state=checked]:border-primary data-[state=checked]:bg-primary h-3.5 w-3.5 rounded-[4px] shadow-none transition-all"
                          />
                        </td>
                        <td className="min-w-0 px-2 py-2">
                          <div className="flex items-center gap-2.5">
                            <FileIcon name={t.file_name} />
                            <div className="min-w-0">
                              <div className="truncate text-sm">
                                {t.file_name}
                              </div>
                              <div className="text-muted-foreground flex items-center gap-1.5 truncate text-xs">
                                <StateBadge
                                  state={t.state}
                                  progress={t.progress}
                                />
                                <span className="uppercase">
                                  {t.file_name.split(".").pop()}
                                </span>
                                <span>·</span>
                                <span>{fmtSize(t.size_bytes)}</span>
                                <span>·</span>
                                <span>
                                  {fmtTime(
                                    (t as { created_at?: string }).created_at,
                                  )}
                                </span>
                              </div>
                            </div>
                          </div>
                        </td>
                        <td className="w-10 px-2 py-2 text-right">
                          <OpsMenu t={t} side="L" />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {(tasksL.data?.total ?? 0) > PAGE_SIZE && (
                <div className="flex items-center justify-center gap-3 py-2 text-sm">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={lPage <= 1}
                    onClick={() => setLPage((p) => p - 1)}
                  >
                    上一页
                  </Button>
                  <span className="text-muted-foreground">
                    {lPage} /{" "}
                    {Math.max(
                      1,
                      Math.ceil((tasksL.data?.total ?? 0) / PAGE_SIZE),
                    )}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={
                      lPage >= Math.ceil((tasksL.data?.total ?? 0) / PAGE_SIZE)
                    }
                    onClick={() => setLPage((p) => p + 1)}
                  >
                    下一页
                  </Button>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* 分隔条（手柄样式对齐对话页 ResizableHandle withHandle） */}
        {collapsed !== "right" && collapsed !== "left" && (
          <div
            className="bg-border relative flex w-px shrink-0 cursor-col-resize items-center justify-center after:absolute after:inset-y-0 after:left-1/2 after:w-2 after:-translate-x-1/2"
            onMouseDown={onSplitDown}
          >
            <div className="bg-border z-10 flex h-4 w-3 items-center justify-center rounded-xs border">
              <GripVerticalIcon className="size-2.5" />
            </div>
          </div>
        )}

        {/* 右：译文区 */}
        <div
          className={cn(
            "flex min-w-0 flex-col",
            collapsed === "right" && "hidden",
          )}
          style={collapsed === "left" ? { flex: 1 } : { flex: 1 }}
        >
          <div className="flex items-center gap-2 border-b px-3 py-2">
            <span className="text-sm font-medium">译文区</span>
            <span className="text-muted-foreground text-xs">
              ZH · 左侧只读镜像
            </span>
            <span className="flex-1" />
            <Button variant="ghost" size="sm" onClick={() => invalidate()}>
              <RefreshCw className="h-3.5 w-3.5" />
            </Button>
            {/* 右全宽切换：左区消失/复原 */}
            <Button
              variant="ghost"
              size="sm"
              className="h-9 w-9 p-0"
              title={collapsed === "left" ? "复原双栏" : "右全宽"}
              onClick={() =>
                setCollapsed(collapsed === "left" ? "none" : "left")
              }
            >
              {collapsed === "left" ? (
                <ArrowRightToLine className="h-4 w-4" />
              ) : (
                <ArrowLeftToLine className="h-4 w-4" />
              )}
            </Button>
          </div>
          <div className="flex min-h-0 flex-1">
            <TreePane side="R" width={rTreeW} />
            <div
              className="hover:bg-muted w-1 shrink-0 cursor-col-resize bg-transparent"
              onMouseDown={startTreeDrag("R")}
            />
            <div className="min-w-0 flex-1 overflow-auto">
              {tasksR.isLoading ? (
                <div className="text-muted-foreground flex items-center gap-2 p-4 text-sm">
                  <Loader2 className="h-4 w-4 animate-spin" /> 加载中…
                </div>
              ) : rTasks.length === 0 ? (
                <div className="text-muted-foreground p-8 text-center text-sm">
                  此文件夹还没有译本。在左侧选择文档点「翻译」，译本会出现在这里。
                </div>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-muted/50 text-muted-foreground border-b text-left text-xs">
                      <th className="px-2 py-2">文件名</th>
                      <th className="w-10 px-2 py-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {rTasks.map((t) => {
                      const inFlight = !["delivered"].includes(t.state);
                      return (
                        <tr
                          key={t.id}
                          className={cn(
                            "hover:bg-muted/50 border-b last:border-b-0",
                            inFlight && "opacity-70",
                          )}
                        >
                          <td className="min-w-0 px-2 py-2">
                            <div className="flex items-center gap-2.5">
                              {inFlight ? (
                                <FilePlus2 className="text-muted-foreground h-4 w-4 shrink-0" />
                              ) : (
                                <FileIcon name={`${t.file_name}.md`} />
                              )}
                              <div className="min-w-0">
                                <div className="truncate text-sm">
                                  {inFlight
                                    ? `${t.file_name}.zh`
                                    : `${t.file_name}.zh.md`}
                                </div>
                                <div className="text-muted-foreground flex items-center gap-1.5 truncate text-xs">
                                  <StateBadge
                                    state={t.state}
                                    progress={t.progress}
                                  />
                                  {inFlight ? (
                                    <>
                                      <span>·</span>
                                      <span>译本生成中</span>
                                    </>
                                  ) : (
                                    <>
                                      <span>·</span>
                                      <span>MD</span>
                                      <span>·</span>
                                      <span>
                                        {fmtTime(
                                          (t as { created_at?: string })
                                            .created_at,
                                        )}
                                      </span>
                                    </>
                                  )}
                                </div>
                              </div>
                            </div>
                          </td>
                          <td className="w-10 px-2 py-2 text-right">
                            {inFlight ? (
                              t.state === "exceeded" ? (
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() =>
                                    flash("ok", "复核工作台建设中（OQ8）")
                                  }
                                >
                                  去复核 →
                                </Button>
                              ) : null
                            ) : (
                              <OpsMenu t={t} side="R" />
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* 统计底栏 */}
      <div className="bg-muted/30 flex flex-wrap items-center gap-4 rounded-md border px-3 py-2 text-sm">
        <span>
          共 <b>{tasksL.data?.total ?? 0}</b>（当前文件夹）
        </span>
        <span>
          待复核 <b>{reviewQ.data?.total ?? 0}</b>
        </span>
        <span className="text-muted-foreground text-xs">
          拖动双栏分隔条调整宽度 · 列表可横向滚动
        </span>
      </div>

      {/* 上传对话框 */}
      <UploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        onUpload={handleUpload}
        uploading={tasksL.isFetching}
        kbOptions={ragKbs.map((k) => ({ id: k.id, name: k.name }))}
        kbId={uploadKbId}
        onKbChange={setUploadKbId}
      />

      {/* 译本预览：双屏对照（左原文 / 右中文译本） */}
      <Dialog
        open={!!previewTask}
        onOpenChange={(v) => !v && setPreviewTask(null)}
      >
        <DialogContent
          className="max-w-none"
          style={{ width: "90vw", height: "90vh", maxWidth: "90vw" }}
        >
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base">
              <FileIcon name={previewTask?.file_name ?? ""} />
              {previewTask?.file_name} · 对照预览
            </DialogTitle>
            <DialogDescription>
              左侧原文 · 右侧中文译本（Markdown 渲染）
            </DialogDescription>
          </DialogHeader>
          <div className="grid h-[calc(90vh-11rem)] min-h-0 grid-cols-2 overflow-hidden rounded-md border">
            <div className="flex min-h-0 flex-col border-r">
              <div className="bg-muted/50 text-muted-foreground border-b px-3 py-1.5 text-xs font-medium">
                原文（
                {(previewTask?.file_name ?? "").split(".").pop()?.toUpperCase()}
                ）
              </div>
              <div className="bg-muted/20 min-h-0 flex-1 overflow-auto">
                {previewTask && (
                  <SourcePreview
                    taskId={previewTask.id}
                    fileName={previewTask.file_name}
                  />
                )}
              </div>
            </div>
            <div className="flex min-h-0 flex-col">
              <div className="bg-muted/50 text-muted-foreground border-b px-3 py-1.5 text-xs font-medium">
                中文译本
              </div>
              <div className="min-h-0 flex-1 overflow-auto p-4">
                {previewLoading ? (
                  <div className="text-muted-foreground flex items-center gap-2 text-sm">
                    <Loader2 className="h-4 w-4 animate-spin" /> 加载中…
                  </div>
                ) : previewMd ? (
                  <div className="size-full overflow-auto px-4 py-3">
                    <SafeStreamdown
                      className="min-w-0"
                      {...artifactMarkdownPlugins}
                    >
                      {previewMd}
                    </SafeStreamdown>
                  </div>
                ) : (
                  <p className="text-muted-foreground text-sm">暂无内容</p>
                )}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" asChild>
              <a
                href={`/api/extensions/translation/tasks/${previewTask?.id}/source`}
              >
                下载原件
              </a>
            </Button>
            <Button asChild>
              <a
                href={`/api/extensions/translation/tasks/${previewTask?.id}/deliverable`}
              >
                下载中文译本
              </a>
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 新建/重命名文件夹 */}
      <Dialog
        open={!!folderDialog}
        onOpenChange={(v) => !v && setFolderDialog(null)}
      >
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>
              {folderDialog?.mode === "create" ? "新建文件夹" : "重命名文件夹"}
            </DialogTitle>
          </DialogHeader>
          <Input
            autoFocus
            placeholder="文件夹名"
            value={folderDialog?.value ?? ""}
            onChange={(e) =>
              setFolderDialog((d) => (d ? { ...d, value: e.target.value } : d))
            }
            onKeyDown={(e) => e.key === "Enter" && submitFolderDialog()}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setFolderDialog(null)}>
              取消
            </Button>
            <Button
              onClick={submitFolderDialog}
              disabled={!folderDialog?.value.trim()}
            >
              保存
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
