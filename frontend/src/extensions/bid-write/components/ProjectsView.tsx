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

import { HelpDrawer } from "@/extensions/bid-write/components/HelpDrawer";
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
import { PROJECTS_COPY } from "@/extensions/bid-write/copy";
import {
  downloadCsv,
  formatDate,
  lifecycleLabel,
  projectSubtitle,
  projectTitle,
  safeProjectTitle,
  taskStatusView,
  TASK_STATUS_LABELS,
} from "@/extensions/bid-write/helpers";
import {
  useBidWriteTasks,
  useCreateBidWriteTask,
} from "@/extensions/bid-write/hooks";
import {
  continueHref,
  continueLabel,
  writeTaskHref,
} from "@/extensions/bid-write/nav";
import type { WriteTaskOut } from "@/extensions/bid-write/types";

const STAGE_TITLES = [
  "①解析确认",
  "②素材核对",
  "③生成配置",
  "④写作工作台",
  "⑤预审查",
  "⑥导出适配",
];

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

export function ProjectsView() {
  const router = useRouter();
  const query = useBidWriteTasks();
  const tasks = query.data?.items ?? [];
  const create = useCreateBidWriteTask();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
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
        safeProjectTitle(projectTitle(task)),
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
              onClick={() => setHelpOpen(true)}
            >
              <Info size={13} aria-hidden="true" />
              流程说明
            </button>
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
                        <b>{safeProjectTitle(projectTitle(task))}</b>
                        <div className="bw-subline">
                          {projectSubtitle(task)}
                        </div>
                      </td>
                      <td className="mono">{task.tender_no ?? "—"}</td>
                      <td className="num">{formatDate(task.created_at)}</td>
                      <td>
                        <div className="bw-stage-cell">
                          <StageDots
                            status={task.status}
                            lifecycle={task.lifecycle}
                            stageTitles={STAGE_TITLES}
                          />
                          <span className="bw-subline">{status.label}</span>
                        </div>
                      </td>
                      <td>
                        <Badge tone={verdict.tone} outline>
                          {verdict.label}
                        </Badge>
                        {task.lifecycle === "reviewing" ? (
                          <Badge tone="info">
                            {lifecycleLabel(task.lifecycle)}
                          </Badge>
                        ) : null}
                        {task.lifecycle === "delivered" ? (
                          <Badge tone="ok">
                            {lifecycleLabel(task.lifecycle)}
                          </Badge>
                        ) : null}
                      </td>
                      <td className="num">
                        {counts
                          ? `${counts.star} / ${counts.blocked}`
                          : task.status === "matrix_ready"
                            ? "—"
                            : "统计中"}
                      </td>
                      <td>
                        <Link href={continueHref(task)} className="btn btn-sm soft">
                          {continueLabel(task)}
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
          <span>{PROJECTS_COPY.intakeNote}</span>
        </div>
      </Overlay>

      <HelpDrawer
        open={helpOpen}
        title="流程说明"
        onClose={() => setHelpOpen(false)}
      >
        <div className="bw-help">
          <p className="bw-help-intro">
            {PROJECTS_COPY.flowIntro}
          </p>
          <div className="bw-help-grid">
            <section
              className="bw-help-section"
              aria-labelledby="bw-flow-governance"
            >
              <h3 id="bw-flow-governance">治理区（跨任务可用）</h3>
              <ul className="bw-help-list">
                <li>
                  <b>资质素材库维护：</b>
                  企业资质、业绩、人员等素材与佐证集中维护；库为空不是错误，缺口会先标为暂无对应素材。
                </li>
                <li>
                  <b>企业档案：</b>
                  企业名称、地址等主体信息集中维护，投标函只引用这里的内容，不补写企业事实。
                </li>
                <li>
                  <b>写作策略：</b>
                  落款、税率、调价、质保期等默认值统一设置，任务里可按项目调整。
                </li>
                <li>
                  <b>质量规则中心：</b>
                  全部质量检查规则一览，可随时查看，导出前按规则判定。
                </li>
              </ul>
            </section>
            <section
              className="bw-help-section"
              aria-labelledby="bw-flow-intake"
            >
              <h3 id="bw-flow-intake">① 解析确认</h3>
              <ol className="bw-help-steps">
                <li>
                  上传的招标文件在此解析成「商务响应矩阵」——每条要求一行，可确认、可纠正、可溯源到原文。
                  带 ★ 的强制条款必须逐条给出响应策略。
                </li>
              </ol>
            </section>
            <section
              className="bw-help-section"
              aria-labelledby="bw-flow-materials"
            >
              <h3 id="bw-flow-materials">② 素材核对</h3>
              <ul className="bw-help-list">
                <li>
                  对照矩阵自动盘点你的资质与业绩素材，提前暴露「暂时拿不出证明」的缺口，避免写完才发现缺件。
                </li>
              </ul>
            </section>
            <section
              className="bw-help-section"
              aria-labelledby="bw-flow-generate"
            >
              <h3 id="bw-flow-generate">③ 生成配置</h3>
              <ul className="bw-help-list">
                <li>
                  录入质保期、报价、签署日期等关键商务参数；系统据此生成投标正文并自动做质量检查。
                </li>
              </ul>
            </section>
            <section
              className="bw-help-section"
              aria-labelledby="bw-flow-editor"
            >
              <h3 id="bw-flow-editor">④ 写作工作台</h3>
              <ul className="bw-help-list">
                <li>
                  像文档一样编辑投标正文：点击占位符直接填写，表格可增删行，审批通过前可反复修改。
                </li>
              </ul>
            </section>
            <section
              className="bw-help-section"
              aria-labelledby="bw-flow-review"
            >
              <h3 id="bw-flow-review">⑤ 预审查</h3>
              <ul className="bw-help-list">
                <li>
                  自动检查正文是否满足全部强制要求；红色问题会阻止导出，处理完即可放行。
                </li>
              </ul>
            </section>
            <section
              className="bw-help-section"
              aria-labelledby="bw-flow-export"
            >
              <h3 id="bw-flow-export">⑥ 导出适配</h3>
              <ul className="bw-help-list">
                <li>
                  最后一道交付检查：矩阵、素材、审批、检查项全部通过后，生成可下载的 DOCX 交付包。
                </li>
              </ul>
            </section>
          </div>
          <div className="bw-help-callout">
            <Info size={15} aria-hidden="true" />
            <span>资质素材库与质量规则中心随时可从左侧进入。</span>
          </div>
        </div>
      </HelpDrawer>
    </>
  );
}
