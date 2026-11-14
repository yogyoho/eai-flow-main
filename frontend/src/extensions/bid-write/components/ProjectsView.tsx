"use client";

import {
  FilePlus2,
  FolderKanban,
  Info,
  RefreshCw,
  UploadCloud,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { toast } from "sonner";

import {
  Badge,
  EmptyState,
  ErrorBlock,
  LoadingBlock,
  MetricCell,
  MetricStrip,
  Overlay,
  PageHead,
  StageDots,
  type Tone,
} from "@/extensions/bid-write/components/primitives";
import {
  downloadCsv,
  formatDate,
  projectSubtitle,
  projectTitle,
  taskStatusView,
  TASK_STATUS_LABELS,
} from "@/extensions/bid-write/helpers";
import {
  useBidWriteTasks,
  useCreateBidWriteTask,
} from "@/extensions/bid-write/hooks";
import { writeTaskHref } from "@/extensions/bid-write/nav";
import type { WriteTaskOut } from "@/extensions/bid-write/types";

function submitability(task: WriteTaskOut): {
  tone: Tone;
  label: string;
} {
  if (task.status === "failed") return { tone: "bad", label: "解析失败" };
  if (task.status !== "matrix_ready") {
    return { tone: "info", label: "处理中" };
  }
  const blocked = task.engine_meta?.matrix_counts?.blocked ?? 0;
  if (blocked > 0) return { tone: "warn", label: `待确认 ${blocked} 项` };
  return { tone: "ok", label: "矩阵已就绪" };
}

function nextHref(task: WriteTaskOut): string {
  // 新任务与失败任务都先落到解析确认页：失败任务在那里看到错误并重试。
  return writeTaskHref("intake", task.id);
}

export function ProjectsView() {
  const router = useRouter();
  const query = useBidWriteTasks();
  const tasks = query.data?.items ?? [];
  const create = useCreateBidWriteTask();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [projectName, setProjectName] = useState("");
  const [lotName, setLotName] = useState("");
  const [tenderNo, setTenderNo] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);

  const ready = tasks.filter((task) => task.status === "matrix_ready").length;
  const active = tasks.filter((task) =>
    ["created", "parsing", "extracting"].includes(task.status),
  ).length;
  const failed = tasks.filter((task) => task.status === "failed").length;

  const resetForm = () => {
    setProjectName("");
    setLotName("");
    setTenderNo("");
    setFiles([]);
    if (fileRef.current) fileRef.current.value = "";
  };

  const submit = async () => {
    if (!projectName.trim()) {
      toast.error("请填写项目名称");
      return;
    }
    if (files.length === 0) {
      toast.error("请选择招标文件");
      return;
    }
    try {
      const task = await create.mutateAsync({
        files,
        projectName: projectName.trim(),
        lotName: lotName.trim(),
        tenderNo: tenderNo.trim(),
      });
      toast.success("写作项目已创建，正在解析招标文件");
      setDialogOpen(false);
      resetForm();
      router.push(writeTaskHref("intake", task.id));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "创建项目失败");
    }
  };

  const exportList = () => {
    if (tasks.length === 0) {
      toast.error("暂无可导出的项目");
      return;
    }
    downloadCsv(
      `投标写作项目-${new Date().toISOString().slice(0, 10)}.csv`,
      ["任务号", "项目名称", "标段", "招标编号", "状态", "创建时间"],
      tasks.map((task) => [
        task.biz_no ?? task.id,
        projectTitle(task),
        task.lot_name ?? "",
        task.tender_no ?? "",
        TASK_STATUS_LABELS[task.status] ?? task.status,
        formatDate(task.created_at),
      ]),
    );
    toast.success("项目列表已导出");
  };

  return (
    <>
      <PageHead
        icon={FolderKanban}
        title="项目列表"
        subtitle="商务部分智能写作 · 从招标文件解析到导出适配"
        actions={
          <>
            <button
              type="button"
              className="btn btn-sm"
              onClick={exportList}
              disabled={tasks.length === 0}
            >
              导出列表
            </button>
            <button
              type="button"
              className="btn pri btn-sm"
              onClick={() => setDialogOpen(true)}
            >
              <FilePlus2 size={14} aria-hidden="true" />
              新建写作项目
            </button>
          </>
        }
      />

      <MetricStrip>
        <MetricCell label="全部项目" value={tasks.length} accent />
        <MetricCell label="矩阵就绪" value={ready} tone="ok" />
        <MetricCell label="解析进行中" value={active} tone="warn" />
        <MetricCell label="解析失败" value={failed} tone="err" />
      </MetricStrip>

      <div className="card">
        <div className="card-h">
          <h3>全部项目</h3>
          <span className="r">
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => void query.refetch()}
              disabled={query.isFetching}
            >
              <RefreshCw
                size={13}
                aria-hidden="true"
                className={query.isFetching ? "bw-spin" : undefined}
              />
              刷新
            </button>
          </span>
        </div>

        {query.isLoading ? (
          <div className="card-b">
            <LoadingBlock label="正在加载写作项目…" />
          </div>
        ) : query.error ? (
          <div className="card-b">
            <ErrorBlock
              error={query.error}
              onRetry={() => void query.refetch()}
            />
          </div>
        ) : tasks.length === 0 ? (
          <div className="card-b">
            <EmptyState
              icon={FolderKanban}
              title="还没有写作项目"
              description="上传招标文件后，系统会抽取商务要素并生成可人工确认的响应矩阵。"
              action={
                <button
                  type="button"
                  className="btn pri"
                  onClick={() => setDialogOpen(true)}
                >
                  新建第一个项目
                </button>
              }
            />
          </div>
        ) : (
          <div className="tbl-wrap">
            <table className="tbl">
              <thead>
                <tr>
                  <th>项目 / 标段</th>
                  <th>招标编号</th>
                  <th>创建时间</th>
                  <th>阶段进度</th>
                  <th>矩阵状态</th>
                  <th>★ / 阻断</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {tasks.map((task) => {
                  const status = taskStatusView(task);
                  const verdict = submitability(task);
                  const counts = task.engine_meta?.matrix_counts;
                  return (
                    <tr key={task.id}>
                      <td>
                        <b>{projectTitle(task)}</b>
                        <div className="bw-subline">
                          {projectSubtitle(task)}
                        </div>
                      </td>
                      <td className="mono">{task.tender_no ?? "—"}</td>
                      <td className="num">{formatDate(task.created_at)}</td>
                      <td>
                        <div className="bw-stage-cell">
                          <StageDots status={task.status} />
                          <span className="bw-subline">{status.label}</span>
                        </div>
                      </td>
                      <td>
                        <Badge tone={verdict.tone} dot>
                          {verdict.label}
                        </Badge>
                      </td>
                      <td className="num">
                        {counts
                          ? `${counts.star} / ${counts.blocked}`
                          : task.status === "matrix_ready"
                            ? "—"
                            : "统计中"}
                      </td>
                      <td>
                        <Link href={nextHref(task)} className="btn btn-sm soft">
                          {task.status === "matrix_ready"
                            ? "进入解析确认"
                            : task.status === "failed"
                              ? "查看失败原因"
                              : "查看进度"}
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="banner info bw-mt">
        <Info size={15} aria-hidden="true" />
        <span>
          主线：每条正文可追溯到招标条款与素材实体；每个缺件在动笔前暴露；每次导出都有门禁明确判定。
        </span>
      </div>

      <Overlay
        open={dialogOpen}
        title="新建写作项目"
        subtitle="上传招标文件"
        onClose={() => {
          if (create.isPending) return;
          setDialogOpen(false);
          resetForm();
        }}
        footer={
          <>
            <button
              type="button"
              className="btn"
              onClick={() => {
                setDialogOpen(false);
                resetForm();
              }}
              disabled={create.isPending}
            >
              取消
            </button>
            <button
              type="button"
              className="btn pri"
              onClick={() => void submit()}
              disabled={create.isPending}
            >
              {create.isPending ? "正在创建…" : "创建并解析"}
            </button>
          </>
        }
      >
        <div className="form-grid">
          <label className="field">
            <span>
              项目名称 <b className="req">*</b>
            </span>
            <input
              className="inp"
              value={projectName}
              onChange={(event) => setProjectName(event.target.value)}
              placeholder="例如：彬长矿区智能化综采装备"
              autoFocus
            />
          </label>
          <label className="field">
            <span>标段 / 包号</span>
            <input
              className="inp"
              value={lotName}
              onChange={(event) => setLotName(event.target.value)}
              placeholder="例如：液压支架与电液控系统"
            />
          </label>
          <label className="field">
            <span>招标编号</span>
            <input
              className="inp"
              value={tenderNo}
              onChange={(event) => setTenderNo(event.target.value)}
              placeholder="例如：ZB-2026-0317"
            />
          </label>
          <label className="field">
            <span>
              招标文件 <b className="req">*</b>
            </span>
            <div className="bw-upload">
              <UploadCloud size={18} aria-hidden="true" />
              <div>
                <b>选择招标文件</b>
                <p>支持 PDF / Word / Excel / PPT；解析在后台进行。</p>
              </div>
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => fileRef.current?.click()}
              >
                浏览
              </button>
              <input
                ref={fileRef}
                type="file"
                multiple
                hidden
                accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.md"
                onChange={(event) =>
                  setFiles(Array.from(event.target.files ?? []))
                }
              />
            </div>
            {files.length > 0 ? (
              <ul className="bw-file-list">
                {files.map((file) => (
                  <li key={`${file.name}-${file.size}`}>
                    <span>{file.name}</span>
                    <span className="mono">
                      {(file.size / 1024 / 1024).toFixed(2)} MB
                    </span>
                  </li>
                ))}
              </ul>
            ) : null}
          </label>
        </div>
        <div className="banner info bw-mt-sm">
          <Info size={15} aria-hidden="true" />
          <span>
            创建后任务会依次执行「解析 → 商务要素抽取 →
            响应矩阵装配」。抽取失败会保留失败原因，不伪造矩阵。
          </span>
        </div>
      </Overlay>
    </>
  );
}
