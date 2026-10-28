"use client";

/**
 * 建库/编辑共用对话框（EAI-CUSTOM，2026-10-18 高保真重构）。
 *
 * 视觉/文案对齐 docs/designs/2026-10-18-translation-kb-dialog-hifi.html：
 * 680px 宽 / 12px 圆角 / 16px 标题 / header + 可滚动 body + 固定 footer；
 * label 中文 + 英文双行，分块配置每项带中文说明与「建议默认」。
 * 行为未变：编辑模式只提交基础+检索字段（v1.0 分块/向量由 pipeline 管理）；
 * 新建提交全套 parser_config。
 */
import { useQuery } from "@tanstack/react-query";
import { Loader2, TriangleAlert } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";

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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

import {
  createRagKb,
  listEmbeddingModels,
  updateRagKb,
  type RagKb,
  type RagKbPayload,
} from "../api";

import { NoteBar, Pill } from "./ui/bits";

const CHUNK_METHODS = [
  "naive",
  "book",
  "laws",
  "paper",
  "qa",
  "manual",
  "table",
  "presentation",
  "one",
] as const;

/** 英文副行（原型 .en / .en-sub）：等宽、10px、弱化。 */
const EN_LINE =
  "block font-mono text-[10px] font-normal tracking-[0.02em] text-muted-foreground/70";
const HELP_LINE = "text-[11px] leading-relaxed text-muted-foreground";

/** 章节标题：中文 13px + 英文副行，右侧可挂徽章。 */
function SectionHeader({
  title,
  en,
  badge,
}: {
  title: string;
  en: string;
  badge?: ReactNode;
}) {
  return (
    <div className="mb-2.5 flex items-center gap-2">
      <h4 className="text-[13px] font-semibold text-muted-foreground">{title}</h4>
      <span className="font-mono text-[10px] tracking-[0.02em] text-muted-foreground/70">
        {en}
      </span>
      {badge ? <span className="ml-auto">{badge}</span> : null}
    </div>
  );
}

/** 「建议默认」提示行（原型 .rec）。 */
function Rec({ children }: { children: ReactNode }) {
  return (
    <p className="flex flex-wrap items-center gap-1.5 text-[11px] leading-snug text-muted-foreground">
      <span className="bg-primary/10 text-primary inline-flex h-4 items-center rounded px-1.5 text-[10px] font-semibold">
        建议默认
      </span>
      <b className="text-foreground font-mono text-[11px] font-semibold">{children}</b>
    </p>
  );
}

/** 双行 label 字段：中文 + 英文副行 + 控件 + 说明 + 建议默认。 */
function Field({
  label,
  en,
  required,
  help,
  rec,
  className,
  children,
}: {
  label: string;
  en: string;
  required?: boolean;
  help?: string;
  rec?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={cn("mb-3 flex flex-col gap-1", className)}>
      <span className="block text-xs font-medium leading-snug text-muted-foreground">
        {label}
        {required ? <span className="text-destructive ml-0.5">*</span> : null}
        <span className={EN_LINE}>{en}</span>
      </span>
      {children}
      {help ? <p className={HELP_LINE}>{help}</p> : null}
      {rec ? <Rec>{rec}</Rec> : null}
    </div>
  );
}

export function RagKbDialog({
  open,
  onOpenChange,
  editing, // null = 新建；RagKb = 编辑
  onSaved,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  editing: RagKb | null;
  onSaved: () => void;
}) {
  const modelsQ = useQuery({
    queryKey: ["tlt-embedding-models"],
    queryFn: listEmbeddingModels,
    enabled: open,
  });
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [language, setLanguage] = useState("Chinese");
  const [permission, setPermission] = useState("team");
  const [embedding, setEmbedding] = useState("");
  const [chunkMethod, setChunkMethod] = useState("naive");
  const [chunkTokenNum, setChunkTokenNum] = useState(512);
  const [delimiter, setDelimiter] = useState("\n");
  const [layoutRecognize, setLayoutRecognize] = useState("DeepDOC");
  const [html4excel, setHtml4excel] = useState(false);
  const [useRaptor, setUseRaptor] = useState(false);
  const [useGraphrag, setUseGraphrag] = useState(false);
  const [useParentChild, setUseParentChild] = useState(false);
  const [tableContextSize, setTableContextSize] = useState(0);
  const [imageContextSize, setImageContextSize] = useState(0);
  const [pagerank, setPagerank] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 打开时回填（编辑：RAGFlow 回读数据；新建：部署默认值）
  useEffect(() => {
    if (!open) return;
    setError(null);
    if (editing) {
      // v1.0：parser_config 已是 pipeline 形状（GeneralChunker/Parser/...），
      // naive 字段回显会显示假默认值——编辑模式不回填、不提交分块子表单
      setName(editing.name);
      setDescription(editing.description ?? "");
      setLanguage(editing.language === "English" ? "English" : "Chinese");
      setPermission(editing.permission === "me" ? "me" : "team");
      setEmbedding(editing.embedding_model ?? "");
      setChunkMethod(editing.chunk_method ?? "naive");
      setPagerank(Number(editing.pagerank ?? 0));
    } else {
      setName("");
      setDescription("");
      setLanguage("Chinese");
      setPermission("team");
      setChunkMethod("naive");
      setChunkTokenNum(512);
      setDelimiter("\n");
      setLayoutRecognize("DeepDOC");
      setHtml4excel(false);
      setUseRaptor(false);
      setUseGraphrag(false);
      setUseParentChild(false);
      setTableContextSize(0);
      setImageContextSize(0);
      setPagerank(0);
    }
  }, [open, editing]);

  // embedding 默认首个可用（新建时）
  useEffect(() => {
    if (open && !editing && !embedding && modelsQ.data?.length)
      setEmbedding(modelsQ.data[0] ?? "");
  }, [open, editing, embedding, modelsQ.data]);

  const buildPayload = (): RagKbPayload => {
    if (editing) {
      // v1.0 编辑模式：分块/向量由 pipeline 管理，只提交基础+检索字段
      // （parser_config/chunk_method/embedding_model 不发送，防默认值覆盖线上配置）
      return {
        description: description || null,
        language,
        permission,
        pagerank,
      };
    }
    const pc: Record<string, unknown> = {
      chunk_token_num: chunkTokenNum,
      delimiter,
      table_context_size: tableContextSize,
      image_context_size: imageContextSize,
    };
    if (chunkMethod === "naive") {
      pc.layout_recognize = layoutRecognize;
      pc.html4excel = html4excel;
      pc.raptor = { use_raptor: useRaptor };
      pc.graphrag = { use_graphrag: useGraphrag };
      pc.parent_child = { use_parent_child: useParentChild };
    } else {
      pc.raptor = { use_raptor: useRaptor };
      pc.graphrag = { use_graphrag: useGraphrag };
    }
    return {
      description: description || null,
      language,
      permission,
      embedding_model: embedding || null,
      chunk_method: chunkMethod,
      parser_config: pc,
      pagerank,
    };
  };

  const save = async () => {
    if (!name.trim() || saving) return;
    setSaving(true);
    setError(null);
    try {
      if (editing) {
        await updateRagKb(editing.id, buildPayload());
      } else {
        await createRagKb({ name: name.trim(), ...buildPayload() });
      }
      onSaved();
      onOpenChange(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const numInput = (
    value: number,
    onChange: (v: number) => void,
    placeholder: string,
    min = 0,
  ) => (
    <Input
      type="number"
      className="h-8 text-[13px]"
      value={value}
      min={min}
      placeholder={placeholder}
      onChange={(e) => onChange(Number(e.target.value))}
    />
  );

  /** 开关行（原型 .switch-row）：说明 + 建议默认，复选框原生控件。 */
  const switchRow = (
    checked: boolean,
    onChange: (v: boolean) => void,
    title: string,
    en: string,
    help: string,
    rec: string,
  ) => (
    <label className="flex cursor-pointer items-start gap-2 border-t border-dashed py-2.5 select-none first:border-t-0">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="accent-primary mt-0.5 h-[15px] w-[15px] shrink-0"
      />
      <span className="min-w-0 flex-1">
        <span className="block text-xs font-medium leading-snug text-foreground">
          {title}
          <span className={EN_LINE}>{en}</span>
        </span>
        <span className={cn("mt-0.5 block", HELP_LINE)}>{help}</span>
        <Rec>{rec}</Rec>
      </span>
    </label>
  );

  const embedDefault = modelsQ.data?.[0];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[88vh] w-full max-w-[680px] flex-col gap-0 overflow-hidden p-0 sm:max-w-[680px]">
        <DialogHeader className="flex-none space-y-0.5 border-b px-5 pt-4 pr-12 pb-3 text-left">
          <DialogTitle className="flex items-center gap-2 text-base leading-snug font-semibold">
            {editing ? `编辑配置 — ${editing.name}` : "新建 RAG 知识库"}
            <Pill tone="gray">RAGFlow</Pill>
          </DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground">
            {editing
              ? "基础与检索字段可编辑；分块/向量由 RAGFlow pipeline 管理。"
              : "创建 dataset 后自动加入翻译体系 · 分块参数在 RAGFlow 1.0 由 pipeline 接管"}
            <span className={cn("mt-0.5", EN_LINE)}>
              {editing
                ? "Edit RAG knowledge base"
                : "Create RAG knowledge base · dataset + translation opt-in"}
            </span>
          </DialogDescription>
        </DialogHeader>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 pt-4 pb-2 text-sm">
          {!editing && (
            <div className="mb-4">
              <NoteBar>
                新建会在 RAGFlow 创建 dataset 并自动加入翻译体系。建库后向量模型与分块配置不可修改；精细调优请到
                RAGFlow 平台。
              </NoteBar>
            </div>
          )}

          {/* A. 基础信息 */}
          <section className="mb-4">
            <SectionHeader title="基础信息" en="Basics" />
            <Field
              label="名称"
              en="Name"
              required
              help="工作台内唯一；同名库会被拒绝。"
              rec={editing ? undefined : "翻译资产库（默认库，上传时自动选择）"}
            >
              <Input
                className="h-8 text-[13px]"
                value={name}
                disabled={!!editing}
                placeholder="例如：铁矿知识库"
                onChange={(e) => setName(e.target.value)}
              />
            </Field>
            <Field
              label="描述（可选）"
              en="Description · Optional"
              help="用于工作台内识别与知识库列表展示。"
            >
              <Input
                className="h-8 text-[13px]"
                value={description}
                placeholder="例如：合资铁矿合同与技术资料"
                onChange={(e) => setDescription(e.target.value)}
              />
            </Field>
            <div className="grid grid-cols-1 gap-x-3.5 sm:grid-cols-2">
              <Field
                label="语言"
                en="Language"
                help="按文档主语言选择；混合语料建议 Chinese。"
                rec={editing ? undefined : "Chinese"}
              >
                <Select value={language} onValueChange={setLanguage}>
                  <SelectTrigger size="sm" className="w-full text-[13px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Chinese">Chinese</SelectItem>
                    <SelectItem value="English">English</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
              <Field
                label="权限"
                en="Permission"
                help="控制知识库在团队内的可见范围。"
                rec={editing ? undefined : "team（团队协作）"}
              >
                <Select value={permission} onValueChange={setPermission}>
                  <SelectTrigger size="sm" className="w-full text-[13px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="team">team（协作可见）</SelectItem>
                    <SelectItem value="me">me（仅自己）</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
            </div>
          </section>

          {/* B. 向量模型 */}
          <section className="mb-4">
            <SectionHeader title="向量模型" en="Embedding model" />
            {editing ? (
              <p className={HELP_LINE}>
                当前：{editing.embedding_model ?? "（自动）"}——RAGFlow 1.0
                建库后不支持更换向量模型。
              </p>
            ) : modelsQ.isLoading ? (
              <span className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" /> 加载模型列表…
              </span>
            ) : (
              <Field
                label="向量模型"
                en="Embedding model"
                required
                help="须与 RAGFlow 已安装的 embedding 模型一致；建库后不可更换。"
                rec={embedDefault ? `${embedDefault}（中文/多语检索）` : "首个可用模型"}
              >
                <Select value={embedding || undefined} onValueChange={setEmbedding}>
                  <SelectTrigger size="sm" className="w-full text-[13px]">
                    <SelectValue placeholder="（自动选择首个可用模型）" />
                  </SelectTrigger>
                  <SelectContent>
                    {(modelsQ.data ?? []).map((m) => (
                      <SelectItem key={m} value={m}>
                        {m}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
            )}
          </section>

          {/* C. 分块配置 */}
          <section className="mb-4">
            <SectionHeader
              title="分块配置"
              en="Chunking"
              badge={<Pill tone="warn">RAGFlow 1.0 pipeline 接管</Pill>}
            />
            {editing ? (
              <p className={HELP_LINE}>
                分块方法：{editing.chunk_method ?? "—"}——RAGFlow 1.0
                建库后不支持修改分块配置，精细调优请到 RAGFlow 平台。
              </p>
            ) : (
              <>
                <div className="bg-muted/30 rounded-lg border px-3.5 pt-3">
                  <div className="grid grid-cols-1 gap-x-3.5 sm:grid-cols-2">
                    <Field
                      label="分块方法"
                      en="Chunk method"
                      help="按文档形态选择解析模板；常规文档用 naive，书籍 book，法规 laws，表格 table。"
                      rec="naive（常规文档）"
                    >
                      <Select value={chunkMethod} onValueChange={setChunkMethod}>
                        <SelectTrigger size="sm" className="w-full text-[13px]">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {CHUNK_METHODS.map((m) => (
                            <SelectItem key={m} value={m}>
                              {m}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </Field>
                    <Field
                      label="分块 token 数"
                      en="Chunk token size"
                      help="单块最大 token 数；越大上下文越完整，召回粒度越粗。"
                      rec="512"
                    >
                      {numInput(chunkTokenNum, setChunkTokenNum, "推荐 512", 1)}
                    </Field>
                    <Field
                      label="分隔符（可选）"
                      en="Delimiter · Optional"
                      help="按该字符切分文本；留空使用 RAGFlow 默认换行。"
                      rec={"\\n（换行）"}
                    >
                      <Input
                        className="h-8 text-[13px]"
                        value={delimiter}
                        placeholder="默认 \n（换行），可填多个字符"
                        onChange={(e) => setDelimiter(e.target.value)}
                      />
                    </Field>
                    {chunkMethod === "naive" && (
                      <>
                        <Field
                          label="版面识别"
                          en="Layout recognition"
                          help="PDF 版面解析器；复杂排版用 DeepDOC，快解析用 Naive，扫描件用 Vision。"
                          rec="DeepDOC（复杂 PDF）"
                        >
                          <Select value={layoutRecognize} onValueChange={setLayoutRecognize}>
                            <SelectTrigger size="sm" className="w-full text-[13px]">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="DeepDOC">DeepDOC</SelectItem>
                              <SelectItem value="Naive">Naive</SelectItem>
                              <SelectItem value="Vision">Vision</SelectItem>
                            </SelectContent>
                          </Select>
                        </Field>
                        <Field
                          label="表格上下文"
                          en="Table context"
                          help="表格前后保留的上下文字符数，避免表头与正文割裂。"
                          rec="0（大多数文档）"
                        >
                          {numInput(
                            tableContextSize,
                            setTableContextSize,
                            "推荐 0（不额外保留）",
                          )}
                        </Field>
                        <Field
                          label="图片上下文"
                          en="Image context"
                          help="图片前后保留的上下文字符数，影响图片说明与正文关联。"
                          rec="0（不额外保留）"
                        >
                          {numInput(
                            imageContextSize,
                            setImageContextSize,
                            "推荐 0（不额外保留）",
                          )}
                        </Field>
                      </>
                    )}
                  </div>

                  {chunkMethod === "naive" &&
                    switchRow(
                      html4excel,
                      setHtml4excel,
                      "Excel 转 HTML",
                      "HTML for Excel",
                      "将 Excel 解析为 HTML 表格，保留合并单元格与样式；大表建议开启。",
                      "关闭（普通文档）",
                    )}
                  {switchRow(
                    useRaptor,
                    setUseRaptor,
                    "RAPTOR 层级摘要",
                    "RAPTOR summaries",
                    "生成层级摘要索引，提升长文档的宏观检索；建库后不可关闭。",
                    "关闭（长报告可开启）",
                  )}
                  {switchRow(
                    useGraphrag,
                    setUseGraphrag,
                    "GraphRAG 知识图谱",
                    "GraphRAG",
                    "抽取实体关系构建知识图谱；耗时与存储开销较高，按需开启。",
                    "关闭",
                  )}
                  {chunkMethod === "naive" &&
                    switchRow(
                      useParentChild,
                      setUseParentChild,
                      "父子分块",
                      "Parent-child chunking",
                      "子块检索、父块回填，兼顾召回精度与上下文完整。",
                      "关闭（超长章节可开启）",
                    )}
                </div>
                <div className="mt-2.5 flex items-start gap-2 rounded-md border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-xs leading-relaxed text-[var(--warning-900)]">
                  <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  <span>
                    当前部署版 RAGFlow 1.0 的分块参数由 pipeline
                    默认值接管，此处配置可能不生效；建库后不可修改，精细调优请到 RAGFlow
                    平台。
                  </span>
                </div>
              </>
            )}
          </section>

          {/* D. 检索 */}
          <section className="mb-4">
            <SectionHeader title="检索" en="Retrieval" />
            <Field
              label="PageRank 权重"
              en="PageRank weight"
              help="RAGFlow 检索排序权重；0 表示使用默认值，一般无需调整。"
              rec="0"
              className="max-w-[260px]"
            >
              {numInput(pagerank, setPagerank, "推荐 0（默认权重）")}
            </Field>
            <p className={HELP_LINE}>
              similarity_threshold / vector_similarity_weight 由部署版 RAGFlow
              接口限制，不可在此修改（默认 0.2 / 0.3）。
            </p>
          </section>

          {error && <p className="text-destructive pb-2 text-xs">{error}</p>}
        </div>

        <DialogFooter className="flex-none flex-row items-center justify-end gap-2 border-t px-5 pt-3 pb-4">
          <span className="mr-auto text-[11px] text-muted-foreground">
            {editing ? "名称不可修改" : "创建后可在知识库列表中继续编辑基础信息"}
          </span>
          <Button
            variant="outline"
            className="h-[30px] px-4 text-[13px]"
            onClick={() => onOpenChange(false)}
          >
            取消
          </Button>
          <Button
            className="h-[30px] px-4 text-[13px]"
            disabled={saving || (!editing && !name.trim())}
            onClick={() => void save()}
          >
            {saving ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : null}
            {editing ? "保存配置" : "创建知识库"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
