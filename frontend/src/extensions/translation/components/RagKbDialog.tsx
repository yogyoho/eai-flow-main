"use client";

import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
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

import {
  createRagKb,
  listEmbeddingModels,
  updateRagKb,
  type RagKb,
  type RagKbPayload,
} from "../api";

/** 建库/编辑共用对话框：全参数（基础/向量/分块/检索）。
 *
 *  编辑模式回显 parser_config（RAGFlow 真源）；raptor/graphrag 只暴露 use 开关
 *  （部署版 REST 边界：similarity_threshold/vector_similarity_weight 不可设，不渲染）。
 */
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
      const pc = editing.parser_config ?? {};
      setName(editing.name);
      setDescription(editing.description ?? "");
      setLanguage(editing.language === "English" ? "English" : "Chinese");
      setPermission(editing.permission === "me" ? "me" : "team");
      setEmbedding(editing.embedding_model ?? "");
      setChunkMethod(editing.chunk_method ?? "naive");
      setChunkTokenNum(Number(pc.chunk_token_num ?? 512));
      setDelimiter(typeof pc.delimiter === "string" ? pc.delimiter : "\n");
      setLayoutRecognize(
        typeof pc.layout_recognize === "string"
          ? pc.layout_recognize
          : "DeepDOC",
      );
      setHtml4excel(pc.html4excel === true);
      setUseRaptor(
        (pc.raptor as Record<string, unknown> | undefined)?.use_raptor === true,
      );
      setUseGraphrag(
        (pc.graphrag as Record<string, unknown> | undefined)?.use_graphrag ===
          true,
      );
      setUseParentChild(
        (pc.parent_child as Record<string, unknown> | undefined)
          ?.use_parent_child === true,
      );
      setTableContextSize(Number(pc.table_context_size ?? 0));
      setImageContextSize(Number(pc.image_context_size ?? 0));
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

  const numInput = (value: number, onChange: (v: number) => void, min = 0) => (
    <Input
      type="number"
      className="h-8 w-28"
      value={value}
      min={min}
      onChange={(e) => onChange(Number(e.target.value))}
    />
  );
  const toggle = (
    checked: boolean,
    onChange: (v: boolean) => void,
    label: string,
  ) => (
    <label className="flex cursor-pointer items-center gap-1.5 text-sm select-none">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="accent-primary"
      />
      {label}
    </label>
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] max-w-xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {editing ? `编辑配置 — ${editing.name}` : "新建 RAG 知识库"}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 text-sm">
          {/* 基础 */}
          <div className="space-y-2">
            <p className="text-muted-foreground text-xs font-medium">基础</p>
            <div className="grid grid-cols-[110px_1fr] items-center gap-2">
              <span>名称{!editing && "*"}</span>
              <Input
                className="h-8"
                value={name}
                disabled={!!editing}
                onChange={(e) => setName(e.target.value)}
              />
              <span>描述</span>
              <Input
                className="h-8"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
              <span>语言</span>
              <Select value={language} onValueChange={setLanguage}>
                <SelectTrigger size="sm" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Chinese">Chinese</SelectItem>
                  <SelectItem value="English">English</SelectItem>
                </SelectContent>
              </Select>
              <span>权限</span>
              <Select value={permission} onValueChange={setPermission}>
                <SelectTrigger size="sm" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="team">team（协作可见）</SelectItem>
                  <SelectItem value="me">me（仅自己）</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* 向量 */}
          <div className="space-y-2">
            <p className="text-muted-foreground text-xs font-medium">
              向量模型
            </p>
            {modelsQ.isLoading ? (
              <span className="text-muted-foreground flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" /> 加载模型列表…
              </span>
            ) : (
              <Select
                value={embedding || undefined}
                onValueChange={setEmbedding}
              >
                <SelectTrigger size="sm" className="w-full">
                  <SelectValue placeholder="（自动选择）" />
                </SelectTrigger>
                <SelectContent>
                  {(modelsQ.data ?? []).map((m) => (
                    <SelectItem key={m} value={m}>
                      {m}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>

          {/* 分块 */}
          <div className="space-y-2">
            <p className="text-muted-foreground text-xs font-medium">
              分块配置
            </p>
            <div className="grid grid-cols-[110px_1fr] items-center gap-2">
              <span>chunk method</span>
              <Select
                value={chunkMethod}
                onValueChange={setChunkMethod}
                disabled={!!editing}
              >
                <SelectTrigger size="sm" className="w-full">
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
              {editing && (
                <span className="text-xs text-muted-foreground">
                  v1.0 不支持建库后修改分块方法
                </span>
              )}
              <span>chunk_token_num</span>
              {numInput(chunkTokenNum, setChunkTokenNum, 1)}
              <span>delimiter</span>
              <Input
                className="h-8 w-28"
                value={delimiter}
                onChange={(e) => setDelimiter(e.target.value)}
              />
              <span>table_context</span>
              {numInput(tableContextSize, setTableContextSize)}
              <span>image_context</span>
              {numInput(imageContextSize, setImageContextSize)}
              {chunkMethod === "naive" && (
                <>
                  <span>layout_recognize</span>
                  <Select
                    value={layoutRecognize}
                    onValueChange={setLayoutRecognize}
                  >
                    <SelectTrigger size="sm" className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="DeepDOC">DeepDOC</SelectItem>
                      <SelectItem value="Naive">Naive</SelectItem>
                      <SelectItem value="Vision">Vision</SelectItem>
                    </SelectContent>
                  </Select>
                  <span>html4excel</span>
                  {toggle(html4excel, setHtml4excel, "Excel 转 HTML 解析")}
                </>
              )}
            </div>
            <div className="flex flex-wrap gap-4 pt-1">
              {toggle(useRaptor, setUseRaptor, "RAPTOR 层级摘要")}
              {toggle(useGraphrag, setUseGraphrag, "GraphRAG 知识图谱")}
              {chunkMethod === "naive" &&
                toggle(useParentChild, setUseParentChild, "父子分块")}
            </div>
            <p className="text-muted-foreground text-xs">
              高级子参（聚类阈值/prompt 等）沿用 RAGFlow
              部署默认；需要精细调优时到 RAGFlow 平台。
            </p>
          </div>

          {/* 检索 */}
          <div className="space-y-2">
            <p className="text-muted-foreground text-xs font-medium">检索</p>
            <div className="grid grid-cols-[110px_1fr] items-center gap-2">
              <span>pagerank</span>
              {numInput(pagerank, setPagerank)}
            </div>
            <p className="text-muted-foreground text-xs">
              similarity_threshold / vector_similarity_weight 由部署版 RAGFlow
              接口限制不可改（默认 0.2 / 0.3）。
            </p>
          </div>

          {error && <p className="text-destructive text-sm">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            disabled={saving || (!editing && !name.trim())}
            onClick={() => void save()}
          >
            {saving ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : null}
            {editing ? "保存配置" : "创建"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
