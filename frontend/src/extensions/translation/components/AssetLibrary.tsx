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
  FileDown,
  FilePlus2,
  FolderPlus,
  FolderRoot,
  GripVerticalIcon,
  History,
  Languages,
  ListPlus,
  Loader2,
  LocateFixed,
  MoreHorizontal,
  Pencil,
  Play,
  RefreshCw,
  ShieldAlert,
  Trash2,
  Upload,
  type LucideIcon,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { FileTypeIcon } from "@/components/file-type-icons";
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
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { artifactMarkdownPlugins } from "@/components/workspace/artifacts/markdown-preview-plugins";
import { SafeStreamdown } from "@/core/streamdown/components";
import { cn } from "@/lib/utils";

import {
  batchTranslateTasks,
  createBackfillJob,
  createFolder,
  deleteFolder,
  deleteTask,
  fetchDeliverablePreview,
  listFolders,
  listRagKbs,
  listTasks,
  moveTaskToFolder,
  patchFolder,
  translateTask,
  uploadAssets,
} from "../api";
import type { TltFolder, TltTask } from "../types";

import { WindowsFolder, WindowsFolderOpen } from "./FolderIcons";
import { PageHeader } from "./PageHeader";
import { SourcePreview } from "./SourcePreview";
import { UploadDialog } from "./UploadDialog";

const PAGE_SIZE = 50;
const POLL_MS = 10_000;

/**
 * 文件名：拉丁字母/数字保持等宽（原型 .mono），中文字符落到系统中文无衬线栈
 * （-apple-system → PingFang / HarmonyOS / 雅黑 / Noto），避免掉进 CJK 等宽宋体。
 */
const FILENAME_FONT =
  "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'HarmonyOS Sans SC', 'Microsoft YaHei', 'Noto Sans SC', sans-serif";

/** 目录树骨架行：缩进深度 + 条宽（对齐 cpa LibraryView 树骨架配方）。 */
const TREE_SKELETON_ROWS = [
  [0, 52],
  [1, 68],
  [2, 56],
  [1, 76],
  [2, 48],
  [1, 60],
  [2, 72],
  [3, 44],
] as const;

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
    document.title = "文件资料库 EN/FR 文档 · 中文译本对照管理";
  }, []);
  const qc = useQueryClient();
  const router = useRouter();
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
  const [lastCheckedId, setLastCheckedId] = useState<string | null>(null);
  const [focusId, setFocusId] = useState<string | null>(null);
  const [backfilling, setBackfilling] = useState(false);
  const headerRef = useRef<HTMLDivElement>(null);
  // 0=全内联；1=回填入更多；2=+翻译；3=+上传；4=+知识库；5=收起搜索框
  const [overflowLevel, setOverflowLevel] = useState(0);
  const [leftActionsInline, setLeftActionsInline] = useState(false);
  const rightHeaderRef = useRef<HTMLDivElement>(null);
  const [rightActionsInline, setRightActionsInline] = useState(false);

  useEffect(() => {
    const el = headerRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width ?? 0;
      setOverflowLevel(
        width >= 760 ? 0 : width >= 680 ? 1 : width >= 600 ? 2 : width >= 520 ? 3 : width >= 440 ? 4 : 5,
      );
      setLeftActionsInline(width >= 560);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const el = rightHeaderRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width ?? 0;
      setRightActionsInline(width >= 560);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  const showBackfillInline = overflowLevel < 1;
  const showTranslateInline = overflowLevel < 2;
  const showUploadInline = overflowLevel < 3;
  const showKbInline = overflowLevel < 4;
  const showSearchInline = overflowLevel < 5;
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

  // flash: sonner 右下角 toast(对齐知识工厂),不再内嵌通知条——列表不位移。
  const flash = (kind: "ok" | "err", text: string) =>
    kind === "ok" ? toast.success(text) : toast.error(text);

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
        const ids = res.filter((item) => !item.reused).map((item) => item.task_id);
        if (ids.length > 0) await batchTranslateTasks(ids);
      }
      invalidate();
      const reused = res.filter((r) => r.reused);
      const created = res.length - reused.length;
      const supersededCount = res.reduce(
        (count, item) => count + (item.superseded?.length ?? 0),
        0,
      );
      if (supersededCount > 0) {
        toast.info(
          `已下线 ${supersededCount} 个旧版本的检索索引（交付物留档）`,
          { duration: 6000 },
        );
      }
      if (reused.length > 0) {
        const createdPart =
          created > 0
            ? `已上传 ${res.length} 个文件：新建 ${created} 个${autoTranslate ? "，已入队" : ""}；`
            : "";
        toast.warning(
          `${createdPart}${reused.length} 个文件内容重复，未新建任务：` +
            reused
              .map(
                (r) =>
                  `${r.file}${r.existing_file ? `（已有：${r.existing_file}）` : ""}`,
              )
              .join("；"),
          { duration: 8000 },
        );
      } else {
        flash(
          "ok",
          `已上传 ${res.length} 个文件（新建翻译任务 ${created} 个${autoTranslate && created ? "，已入队" : ""}）`,
        );
      }
      return { total: files.length, failed: [] as File[], reused };
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
      const res = await batchTranslateTasks(translatable.map((t) => t.id));
      invalidate();
      setChecked(new Set());
      flash(
        "ok",
        res.queued === translatable.length
          ? `已提交 ${res.queued} 个翻译任务`
          : `已提交 ${res.queued} 个；${res.skipped.length} 个状态已变化被跳过`,
      );
    } catch (e) {
      flash("err", `提交失败：${e instanceof Error ? e.message : String(e)}`);
    }
  };

  /** P2 超大回填：当前库/文件夹下的未翻译任务分批入队。 */
  const startBackfill = async () => {
    setBackfilling(true);
    try {
      const job = await createBackfillJob({
        kb_id: kbFilter === "all" ? undefined : kbFilter,
        folder_id:
          lFolder === "root" ? "root" : (lFolder ?? undefined),
        states: ["stored", "failed"],
        chunk_size: 100,
      });
      invalidate();
      flash(
        "ok",
        `已创建回填任务（${job.total} 个，每批 ${job.chunk_size} 个入队）`,
      );
    } catch (e) {
      flash("err", `回填失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBackfilling(false);
    }
  };

  const doDelete = async (t: TltTask) => {
    if (!window.confirm(`删除「${t.file_name}」？将下线检索索引，交付物文件保留。`))
      return;
    try {
      await deleteTask(t.id);
      invalidate();
      const s = new Set(checked);
      s.delete(t.id);
      setChecked(s);
      flash("ok", "已删除并下线检索（交付物留档）");
    } catch (e) {
      flash("err", `删除失败：${e instanceof Error ? e.message : String(e)}`);
    }
  };

  /** Shift 连选：基于当前页文件顺序（P2-16）。 */
  const toggleChecked = (id: string, shiftKey: boolean) => {
    setChecked((prev) => {
      const next = new Set(prev);
      if (shiftKey && lastCheckedId) {
        const ids = lTasks.map((item) => item.id);
        const a = ids.indexOf(lastCheckedId);
        const b = ids.indexOf(id);
        if (a >= 0 && b >= 0) {
          const [lo, hi] = a < b ? [a, b] : [b, a];
          const shouldCheck = !prev.has(id);
          for (let i = lo; i <= hi; i += 1) {
            const tid = ids[i];
            if (!tid) continue;
            if (shouldCheck) next.add(tid);
            else next.delete(tid);
          }
          return next;
        }
      }
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    setLastCheckedId(id);
  };

  const moveToFolder = async (taskId: string, folderId: FolderId) => {
    try {
      await moveTaskToFolder(taskId, folderId === "root" ? null : folderId);
      invalidate();
      flash("ok", "已移动文件");
    } catch (e) {
      flash("err", `移动失败：${e instanceof Error ? e.message : String(e)}`);
    }
  };

  /** 左/右栏配对定位：切到对应文件夹并滚动到目标行。 */
  const locatePair = (t: TltTask, from: "L" | "R") => {
    const target = (t.folder_id ?? "root") as FolderId;
    if (from === "L") {
      setRFolder(target);
    } else {
      setLFolder(target);
      setRFolder(target);
      setLPage(1);
    }
    setFocusId(t.id);
    const rowId = `${from === "L" ? "rtask" : "ltask"}-${t.id}`;
    window.setTimeout(() => {
      document.getElementById(rowId)?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 150);
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
        // 虚拟根 "root" 不是后端 UUID；建在根目录时 parent_id 必须为 null
        const parentId =
          folderDialog.parent === "root"
            ? null
            : (folderDialog.parent ?? null);
        await createFolder(folderDialog.value.trim(), parentId);
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
            onDragOver={(e) => {
              e.preventDefault();
              e.dataTransfer.dropEffect = "move";
            }}
            onDrop={(e) => {
              e.preventDefault();
              e.stopPropagation();
              const taskId = e.dataTransfer.getData("application/x-tlt-task");
              if (taskId) void moveToFolder(taskId, n.id);
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
              <WindowsFolderOpen className="h-4 w-4 shrink-0 drop-shadow-sm" />
            ) : (
              <WindowsFolder className="h-4 w-4 shrink-0 drop-shadow-sm" />
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
      /* 与 cpa 合同文件库一致：根目录图标 / 文件夹 / 子文件夹 */
      <span className="text-muted-foreground flex flex-wrap items-center gap-1 text-xs pt-1">
        <FolderRoot className="h-3.5 w-3.5 shrink-0" aria-hidden />
        <span className="px-0.5">/</span>
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
      </span>
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
          <TreeSkeleton />
        ) : (
          renderTree(displayTree, 0, side)
        )}
      </div>
    );
  };

  /** 目录树骨架：8 行缩进脉冲条，模拟层级与目录名。 */
  const TreeSkeleton = () => (
    <div role="status" aria-label="文件夹加载中" className="space-y-2.5 p-2">
      {TREE_SKELETON_ROWS.map(([depth, w], i) => (
        <div
          key={i}
          aria-hidden
          className="flex items-center gap-1.5"
          style={{ paddingLeft: depth * 12 }}
        >
          <div className="bg-muted-foreground/15 size-3 shrink-0 animate-pulse rounded-sm" />
          <div
            className="bg-muted-foreground/15 h-3 animate-pulse rounded"
            style={{ width: w }}
          />
        </div>
      ))}
    </div>
  );

  /** 文件列表骨架：列形对齐当前表（勾选 / 文件名+状态 / 操作）。 */
  const TableSkeleton = ({ withCheckbox = false }: { withCheckbox?: boolean }) => (
    <div role="status" aria-label="文件列表加载中">
      <table className="w-full text-sm" aria-hidden>
        <thead>
          <tr className="bg-muted/50 text-muted-foreground border-b text-left text-xs">
            {withCheckbox && <th className="w-8 px-2 py-2" />}
            <th className="px-2 py-2">文件名</th>
            <th className="w-10 px-2 py-2" />
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: 8 }, (_, i) => (
            <tr
              key={i}
              className="border-b border-[var(--gray-100)] last:border-b-0"
            >
              {withCheckbox && (
                <td className="w-8 px-2 py-2">
                  <div className="bg-muted-foreground/15 size-3.5 animate-pulse rounded-sm" />
                </td>
              )}
              <td className="min-w-0 px-2 py-2">
                <div className="flex items-center gap-2.5">
                  <div className="bg-muted-foreground/15 size-5 shrink-0 animate-pulse rounded" />
                  <div className="min-w-0 space-y-1.5">
                    <div
                      className="bg-muted-foreground/15 h-3.5 animate-pulse rounded"
                      style={{ width: 140 + (i % 3) * 28 }}
                    />
                    <div
                      className="bg-muted-foreground/15 h-3 animate-pulse rounded"
                      style={{ width: 88 + (i % 4) * 18 }}
                    />
                  </div>
                </div>
              </td>
              <td className="w-10 px-2 py-2">
                <div className="bg-muted-foreground/15 ml-auto size-4 animate-pulse rounded" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  const queueTranslate = (t: TltTask) => {
    void translateTask(t.id)
      .then(() => {
        invalidate();
        flash("ok", "已加入翻译队列");
      })
      .catch((e) => flash("err", String(e)));
  };

  type RowAction = {
    key: string;
    label: string;
    icon: LucideIcon;
    run?: () => void;
    href?: string;
    danger?: boolean;
  };

  const rowActions = (t: TltTask, side: "L" | "R"): RowAction[] => {
    const actions: RowAction[] = [];
    if (side === "L" && (t.state === "stored" || t.state === "failed")) {
      actions.push({
        key: "translate",
        label: "翻译",
        icon: Play,
        run: () => queueTranslate(t),
      });
    }
    actions.push({
      key: "source",
      label: "下载原件",
      icon: Download,
      href: `/api/extensions/translation/tasks/${t.id}/source`,
    });
    if (side === "L" && t.state === "delivered") {
      actions.push({
        key: "locate",
        label: "定位译文",
        icon: LocateFixed,
        run: () => locatePair(t, "L"),
      });
    }
    if (side === "R") {
      actions.push({
        key: "locate",
        label: "定位原文",
        icon: LocateFixed,
        run: () => locatePair(t, "R"),
      });
    }
    if (side === "R" && t.state === "delivered") {
      actions.push({
        key: "preview",
        label: "预览",
        icon: Eye,
        run: () => openPreview(t),
      });
      actions.push({
        key: "deliverable",
        label: "下载译文",
        icon: FileDown,
        href: `/api/extensions/translation/tasks/${t.id}/deliverable`,
      });
    }
    actions.push({
      key: "delete",
      label: "删除文档",
      icon: Trash2,
      run: () => void doDelete(t),
      danger: true,
    });
    return actions;
  };

  /** 行操作：宽栏内联图标按钮，窄栏收进「···」下拉。 */
  const RowActions = ({
    t,
    side,
    inline,
  }: {
    t: TltTask;
    side: "L" | "R";
    inline: boolean;
  }) => {
    const actions = rowActions(t, side);
    if (!inline) {
      return (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" className="h-7 w-7 p-0">
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {actions.map((action) => {
              const Icon = action.icon;
              if (action.href) {
                return (
                  <DropdownMenuItem key={action.key} asChild>
                    <a href={action.href}>
                      <Icon className="mr-2 h-4 w-4" /> {action.label}
                    </a>
                  </DropdownMenuItem>
                );
              }
              return (
                <DropdownMenuItem
                  key={action.key}
                  className={action.danger ? "text-destructive" : undefined}
                  onClick={action.run}
                >
                  <Icon className="mr-2 h-4 w-4" /> {action.label}
                </DropdownMenuItem>
              );
            })}
          </DropdownMenuContent>
        </DropdownMenu>
      );
    }
    return (
      <div className="flex items-center justify-end gap-0.5">
        {actions.map((action) => {
          const Icon = action.icon;
          const cls = cn(
            "inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
            action.danger &&
              "text-destructive hover:bg-destructive/10 hover:text-destructive",
          );
          if (action.href) {
            return (
              <a
                key={action.key}
                href={action.href}
                className={cls}
                title={action.label}
                aria-label={action.label}
              >
                <Icon className="h-3.5 w-3.5" />
              </a>
            );
          }
          return (
            <button
              key={action.key}
              type="button"
              className={cls}
              title={action.label}
              aria-label={action.label}
              onClick={action.run}
            >
              <Icon className="h-3.5 w-3.5" />
            </button>
          );
        })}
      </div>
    );
  };

  return (
    <div className="flex h-full flex-col gap-3 px-4 pt-3 pb-4">
      <PageHeader
        title="文件资料库"
        description={
          <Crumbs
            folderId={lFolder}
            onPick={(id) => {
              setLFolder(id);
              setRFolder(id);
              setLPage(1);
            }}
          />
        }
        icon={<Languages />}
        topRight="EN/FR 文档 · 中文译本对照管理"
        actions={
          reviewQ.data && reviewQ.data.total > 0 ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => router.push("/translation/review")}
            >
              待复核 {reviewQ.data.total} →
            </Button>
          ) : undefined
        }
      />

      {/* 双栏 */}
      <div
        ref={splitRef}
        className="flex min-h-0 flex-1 overflow-hidden rounded-lg border"
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
          <div
            ref={headerRef}
            className="flex flex-wrap items-center gap-2 border-b px-3 py-2"
          >
            <span className="shrink-0 text-sm font-medium">原文区</span>
            <span className="text-muted-foreground shrink-0 font-mono text-xs">
              EN/FR
            </span>
            <span className="min-w-2 flex-1" />
            {showSearchInline && (
              <Input
                placeholder="搜索 文件名 / sha"
                className="h-8 w-40 min-w-20 shrink text-[13px]"
                value={q}
                onChange={(e) => {
                  setQ(e.target.value);
                  setLPage(1);
                }}
              />
            )}
            {showKbInline && (
              <Select
                value={kbFilter}
                onValueChange={(v) => {
                  setKbFilter(v);
                  setLPage(1);
                }}
              >
                <SelectTrigger
                  size="sm"
                  className="w-32 shrink-0 text-[13px]"
                  aria-label="知识库筛选"
                >
                  <SelectValue placeholder="全部库" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all" className="text-[13px]">
                    全部库
                  </SelectItem>
                  {ragKbs.map((k) => (
                    <SelectItem key={k.id} value={k.id} className="text-[13px]">
                      {k.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            {showUploadInline && (
              <Button
                variant="outline"
                size="sm"
                className="text-[13px]"
                onClick={() => setUploadOpen(true)}
              >
                <Upload className="mr-1 h-3 w-3" /> 上传
              </Button>
            )}
            {showTranslateInline && (
              <Button
                size="sm"
                className="text-[13px] tabular-nums"
                disabled={!translatable.length}
                onClick={doTranslateChecked}
              >
                {tasksL.isFetching ? (
                  <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                ) : (
                  <Play className="mr-1 h-3 w-3" />
                )}
                翻译 ({translatable.length})
              </Button>
            )}
            {showBackfillInline && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-[13px]"
                    disabled={backfilling}
                    onClick={() => void startBackfill()}
                  >
                    {backfilling ? (
                      <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                    ) : (
                      <ListPlus className="mr-1 h-3 w-3" />
                    )}
                    回填
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="bottom" className="max-w-72">
                  把当前知识库/文件夹下未翻译和翻译失败的文档分批加入队列，后台按批处理；已交付文件不受影响。
                </TooltipContent>
              </Tooltip>
            )}
            {overflowLevel > 0 && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-8 w-8 shrink-0 p-0"
                    aria-label="更多操作"
                  >
                    <svg
                      aria-hidden
                      className="h-4 w-4"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <path d="M3 5h11" />
                      <path d="M3 12h11" />
                      <path d="M3 19h11" />
                      <path d="M19 5v14" />
                      <path d="m15 15 4 4 4-4" />
                    </svg>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent
                  align="end"
                  className="max-h-80 w-56 overflow-y-auto"
                >
                  {!showUploadInline && (
                    <DropdownMenuItem onSelect={() => setUploadOpen(true)}>
                      <Upload className="mr-2 h-4 w-4" /> 上传文件
                    </DropdownMenuItem>
                  )}
                  {!showTranslateInline && (
                    <DropdownMenuItem
                      disabled={!translatable.length}
                      onSelect={() => void doTranslateChecked()}
                    >
                      <Play className="mr-2 h-4 w-4" /> 翻译已勾选（
                      {translatable.length}）
                    </DropdownMenuItem>
                  )}
                  {!showBackfillInline && (
                    <DropdownMenuItem
                      disabled={backfilling}
                      onSelect={() => void startBackfill()}
                    >
                      <ListPlus className="mr-2 h-4 w-4" /> 回填未翻译
                    </DropdownMenuItem>
                  )}
                  {!showKbInline && (
                    <>
                      <DropdownMenuSeparator />
                      <DropdownMenuLabel className="text-muted-foreground text-[11px]">
                        知识库
                      </DropdownMenuLabel>
                      <DropdownMenuRadioGroup
                        value={kbFilter}
                        onValueChange={(v) => {
                          setKbFilter(v);
                          setLPage(1);
                        }}
                      >
                        <DropdownMenuRadioItem value="all">
                          全部库
                        </DropdownMenuRadioItem>
                        {ragKbs.map((k) => (
                          <DropdownMenuRadioItem key={k.id} value={k.id}>
                            {k.name}
                          </DropdownMenuRadioItem>
                        ))}
                      </DropdownMenuRadioGroup>
                    </>
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
            )}
            {/* 左全宽切换：固定保留在标题区最右侧，不随窄屏收进「更多」 */}
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 shrink-0 p-0"
              title={collapsed === "right" ? "复原双栏" : "左全宽"}
              onClick={() =>
                setCollapsed(collapsed === "right" ? "none" : "right")
              }
            >
              {collapsed === "right" ? (
                <ArrowLeftToLine className="h-3.5 w-3.5" />
              ) : (
                <ArrowRightToLine className="h-3.5 w-3.5" />
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
                <TableSkeleton withCheckbox />
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
                      <th
                        className={cn(
                          "px-2 py-2",
                          leftActionsInline ? "w-32" : "w-10",
                        )}
                      />
                    </tr>
                  </thead>
                  <tbody>
                    {lTasks.map((t) => (
                      <tr
                        key={t.id}
                        id={`ltask-${t.id}`}
                        draggable
                        onDragStart={(e) => {
                          e.dataTransfer.setData("application/x-tlt-task", t.id);
                          e.dataTransfer.effectAllowed = "move";
                        }}
                        className={cn(
                          "hover:bg-muted/50 border-b border-[var(--gray-100)] last:border-b-0",
                          focusId === t.id && "bg-primary/5",
                        )}
                      >
                        <td className="px-2 py-2">
                          <Checkbox
                            checked={checked.has(t.id)}
                            onChange={(e) =>
                              toggleChecked(
                                t.id,
                                (e.nativeEvent as MouseEvent).shiftKey,
                              )
                            }
                            className="border-muted-foreground/40 hover:border-primary data-[state=checked]:border-primary data-[state=checked]:bg-primary h-3.5 w-3.5 rounded-[4px] shadow-none transition-all"
                          />
                        </td>
                        <td className="min-w-0 px-2 py-2">
                          <div className="flex items-center gap-2.5">
                            <FileTypeIcon
                              name={t.file_name}
                              className="h-7 w-7 shrink-0"
                            />
                            <div className="min-w-0">
                              <div className="truncate" style={{ fontFamily: FILENAME_FONT }}>
                                {t.file_name}
                              </div>
                              <div className="text-muted-foreground flex items-center gap-1.5 truncate text-xs">
                                <StateBadge
                                  state={t.state}
                                  progress={t.progress}
                                />
                                <span className="font-mono uppercase">
                                  {t.file_name.split(".").pop()}
                                </span>
                                <span>·</span>
                                <span className="font-mono tabular-nums">
                                  {fmtSize(t.size_bytes)}
                                </span>
                                <span>·</span>
                                <span className="font-mono tabular-nums">
                                  {fmtTime(
                                    (t as { created_at?: string }).created_at,
                                  )}
                                </span>
                              </div>
                            </div>
                          </div>
                        </td>
                        <td
                          className={cn(
                            "px-2 py-2 text-right",
                            leftActionsInline ? "w-32" : "w-10",
                          )}
                        >
                          <RowActions
                            t={t}
                            side="L"
                            inline={leftActionsInline}
                          />
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
          <div
            ref={rightHeaderRef}
            className="flex items-center gap-2 border-b px-3 py-2"
          >
            <span className="text-sm font-medium">译文区</span>
            <span className="text-muted-foreground text-xs">
              <span className="font-mono">ZH</span> · 左侧只读镜像
            </span>
            <span className="flex-1" />
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0"
              onClick={() => invalidate()}
            >
              <RefreshCw className="h-3 w-3" />
            </Button>
            {/* 右全宽切换：左区消失/复原 */}
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0"
              title={collapsed === "left" ? "复原双栏" : "右全宽"}
              onClick={() =>
                setCollapsed(collapsed === "left" ? "none" : "left")
              }
            >
              {collapsed === "left" ? (
                <ArrowRightToLine className="h-3.5 w-3.5" />
              ) : (
                <ArrowLeftToLine className="h-3.5 w-3.5" />
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
                <TableSkeleton />
              ) : rTasks.length === 0 ? (
                <div className="text-muted-foreground p-8 text-center text-sm">
                  此文件夹还没有译本。在左侧选择文档点「翻译」，译本会出现在这里。
                </div>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-muted/50 text-muted-foreground border-b text-left text-xs">
                      <th className="px-2 py-2">文件名</th>
                      <th
                        className={cn(
                          "px-2 py-2",
                          rightActionsInline ? "w-40" : "w-24",
                        )}
                      />
                    </tr>
                  </thead>
                  <tbody>
                    {rTasks.map((t) => {
                      const inFlight = !["delivered"].includes(t.state);
                      return (
                        <tr
                          key={t.id}
                          id={`rtask-${t.id}`}
                          className={cn(
                            "hover:bg-muted/50 border-b border-[var(--gray-100)] last:border-b-0",
                            inFlight && "opacity-70",
                            focusId === t.id && "bg-primary/5",
                          )}
                        >
                          <td className="min-w-0 px-2 py-2">
                            <div className="flex items-center gap-2.5">
                              {inFlight ? (
                                <FilePlus2 className="text-muted-foreground h-4 w-4 shrink-0" />
                              ) : (
                                <FileTypeIcon
                                  name={`${t.file_name}.md`}
                                  className="h-7 w-7 shrink-0"
                                />
                              )}
                              <div className="min-w-0">
                                <div className="truncate" style={{ fontFamily: FILENAME_FONT }}>
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
                                      <span className="font-mono">MD</span>
                                      <span>·</span>
                                      <span className="font-mono tabular-nums">
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
                          <td
                            className={cn(
                              "px-2 py-2 text-right",
                              rightActionsInline ? "w-40" : "w-24",
                            )}
                          >
                            {inFlight ? (
                              t.state === "exceeded" ? (
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() =>
                                    router.push(
                                      `/translation/review?task_id=${t.id}`,
                                    )
                                  }
                                >
                                  去复核 →
                                </Button>
                              ) : null
                            ) : (
                              <RowActions
                                t={t}
                                side="R"
                                inline={rightActionsInline}
                              />
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
      <div className="bg-muted/30 flex flex-wrap items-center gap-4 rounded-md border px-3 py-2 text-sm tabular-nums">
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
              <FileTypeIcon
                name={previewTask?.file_name ?? ""}
                className="h-5 w-5 shrink-0"
              />
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
