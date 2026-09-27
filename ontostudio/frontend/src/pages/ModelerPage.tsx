/**
 * 05 本体建模器（EAI-CUSTOM, 2026-09-27 原型还原 + 批次 2 画布交互转正）。
 *
 * 骨架 = 三栏（域文件列表 | 编辑器单面板 | 右栏 300px），双模式：
 * - 可视化模式：TBox 画布（真实类层次 + 实例计数 + 属性链）——节点**可拖拽移位**
 *   （视图态，registry 无布局数据不落 YAML，随域切换重置）；「＋子类」进入连线模式
 *   （点选父类完成 subClassOf 加边，写 parents 草稿）；表单父类 chips 可增删（=边编辑）；
 *   新建类实装（草稿追加 + 画布居中出现）。
 * - YAML 源码模式：行号编辑器（结构编辑兜底，schema 校验兜底）。
 * 编辑管线：表单/画布/YAML 均落 draftText（单一草稿）→ 校验 → 保存（fingerprint 乐观
 * 并发 + registry_version 递增 + SHA 热重载）。
 */
import { useQuery, useQueryClient, useQueries } from "@tanstack/react-query";
import { DraftingCompass, Loader2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { load as yamlLoad, dump as yamlDump } from "js-yaml";

import { fetchAggregate } from "@/api/ontology-graph-api";
import {
  fetchRegistryContent,
  fetchRegistryFiles,
  saveRegistryContent,
  validateRegistryDraft,
  type RegistryAxioms,
} from "@/api/registry-api";
import { Chip, PageHeader, Panel } from "@/pages/shared";
import { cn } from "@/lib/utils";
import { withAlpha } from "@/explorer/graphTheme";

const TONE_BLUE = "#0746ff";
const AMBER = "#faad14";

interface ClassEntry {
  name: string;
  label: string;
  definition: string;
  parents: string[];
  hasKey: string[];
  etypes: string[];
}

function buildTree(classes: ClassEntry[]) {
  const byName = new Map(classes.map((c) => [c.name, c]));
  const children = new Map<string, string[]>();
  const roots: string[] = [];
  for (const c of classes) {
    const rp = c.parents.filter((p) => byName.has(p));
    if (rp.length === 0) roots.push(c.name);
    else
      for (const p of rp) {
        const l = children.get(p) ?? [];
        l.push(c.name);
        children.set(p, l);
      }
  }
  const out: Array<{ cls: ClassEntry; depth: number }> = [];
  const seen = new Set<string>();
  const walk = (name: string, depth: number) => {
    if (seen.has(name)) return;
    seen.add(name);
    const e = byName.get(name);
    if (!e) return;
    out.push({ cls: e, depth });
    for (const ch of children.get(name) ?? []) walk(ch, depth + 1);
  };
  for (const n of roots) walk(n, 0);
  for (const c of classes)
    if (!seen.has(c.name)) out.push({ cls: c, depth: 0 });
  return out;
}

type Draft = Record<string, unknown>;
interface Pos {
  x: number;
  y: number;
}

export function ModelerPage() {
  const qc = useQueryClient();
  const [selectedFile, setSelectedFile] = useState("doc_graph.yaml");
  const [selectedClass, setSelectedClass] = useState<string | null>(null);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [mode, setMode] = useState<"vis" | "yaml">("vis");
  const [busy, setBusy] = useState(false);

  const contentQuery = useQuery({
    queryKey: ["registry-content", selectedFile],
    queryFn: () => fetchRegistryContent(selectedFile),
    staleTime: 30_000,
  });
  const content = contentQuery.data;
  const domainName = useMemo(() => selectedFile.replace(/\.yaml$/, ""), [selectedFile]);
  const domainSummary = content?.summary?.domains?.[domainName] ?? null;
  const axioms = content?.summary?.axioms?.[domainName];
  const domainPredicates = domainSummary?.predicates ?? [];

  // 草稿文本：null = 与远端一致
  const [draftText, setDraftText] = useState<string | null>(null);
  useEffect(() => {
    setDraftText(null);
    setSelectedClass(null);
    setPositionOverrides(new Map()); // 位置是视图态，随域切换重置
    setConnectChild(null);
  }, [content?.raw, selectedFile]);

  const remoteText = content?.raw ?? "";
  const text = draftText ?? remoteText;
  const dirty = draftText !== null && draftText !== remoteText;

  const allClasses: ClassEntry[] = useMemo(() => {
    if (!domainSummary) return [];
    return domainSummary.classes.map((c) => ({
      name: c.name,
      label: c.label,
      definition: c.definition,
      parents: c.parents,
      hasKey: c.hasKey,
      etypes: c.etypes ?? [],
    }));
  }, [domainSummary]);
  const selected = allClasses.find((c) => c.name === selectedClass) ?? null;

  // 实例计数（按域过滤 etype 聚合）
  const etypeCountQuery = useQuery({
    queryKey: ["ontology", "aggregate", "graph_entity", "etype", domainName],
    queryFn: ({ signal }) =>
      fetchAggregate("graph_entity", "etype", {
        limit: 200,
        filters: [{ column: "domain", op: "eq", value: domainName }],
        signal,
      }),
    enabled: allClasses.length > 0,
    staleTime: 60_000,
  });
  const countByEtype = useMemo(() => {
    const map = new Map<string, number>();
    for (const row of etypeCountQuery.data ?? []) {
      if (row.group) map.set(row.group, row.value);
    }
    return map;
  }, [etypeCountQuery.data]);
  const instancesOf = useCallback(
    (cls: ClassEntry): number | null => {
      const keys = cls.etypes.length > 0 ? cls.etypes : [cls.name.toLowerCase()];
      const known = keys.some((k) => countByEtype.has(k));
      if (!known) return null;
      return keys.reduce((sum, k) => sum + (countByEtype.get(k) ?? 0), 0);
    },
    [countByEtype],
  );

  // 基础布局（继承深度分层）；用户拖拽写 overrides，读时覆盖
  const baseLayout = useMemo(() => {
    const layers = new Map<number, ClassEntry[]>();
    for (const { cls, depth } of buildTree(allClasses)) {
      const list = layers.get(depth) ?? [];
      list.push(cls);
      layers.set(depth, list);
    }
    const rows = [...layers.keys()].sort((a, b) => a - b);
    const positions = new Map<string, Pos>();
    rows.forEach((depth, rowIdx) => {
      const row = layers.get(depth) ?? [];
      const n = row.length;
      row.forEach((cls, i) => {
        positions.set(cls.name, {
          x: 8 + ((i + 1) * 84) / (n + 1),
          y:
            rows.length === 1
              ? 50
              : 12 + rowIdx * (76 / Math.max(1, rows.length - 1)),
        });
      });
    });
    return positions;
  }, [allClasses]);

  const [positionOverrides, setPositionOverrides] = useState<Map<string, Pos>>(
    new Map(),
  );
  const effectivePositions = useMemo(() => {
    const merged = new Map(baseLayout);
    positionOverrides.forEach((pos, name) => {
      if (baseLayout.has(name) || allClasses.some((c) => c.name === name)) {
        merged.set(name, pos);
      }
    });
    return merged;
  }, [baseLayout, positionOverrides, allClasses]);

  // 草稿变更统一入口
  const mutateDraft = useCallback(
    (mutate: (obj: Draft) => void): boolean => {
      try {
        const obj = yamlLoad(text) as Draft;
        mutate(obj);
        setDraftText(yamlDump(obj, { lineWidth: -1 }));
        setSaveMsg(null);
        return true;
      } catch {
        setSaveMsg("✗ 当前文本不是合法 YAML，表单编辑不可用——请先在 YAML 模式修正");
        return false;
      }
    },
    [text],
  );

  const editClassField = useCallback(
    (clsName: string, field: "label" | "definition", value: string) => {
      mutateDraft((obj) => {
        const classes = (obj.classes ?? {}) as Draft;
        const entry = (classes[clsName] ?? {}) as Draft;
        classes[clsName] = { ...entry, [field]: value };
        obj.classes = classes;
      });
    },
    [mutateDraft],
  );

  const addClass = useCallback(() => {
    let name = "";
    const ok = mutateDraft((obj) => {
      const classes = (obj.classes ?? {}) as Draft;
      let n = 1;
      while (classes[`NewClass_${n}`]) n += 1;
      name = `NewClass_${n}`;
      classes[name] = { label: "新类（未命名）", parents: [] };
      obj.classes = classes;
    });
    if (ok) {
      setSelectedClass(name);
      setPositionOverrides((prev) => {
        const next = new Map(prev);
        next.set(name, { x: 50, y: 85 });
        return next;
      });
      setSaveMsg(`✓ 已在草稿追加 ${name}——命名/父类可继续编辑，保存前须过校验`);
    }
  }, [mutateDraft]);

  const removeClass = useCallback(
    (clsName: string) => {
      const ok = mutateDraft((obj) => {
        const classes = { ...((obj.classes ?? {}) as Draft) };
        delete classes[clsName];
        obj.classes = classes;
      });
      if (ok) {
        setSelectedClass(null);
        setPositionOverrides((prev) => {
          const next = new Map(prev);
          next.delete(clsName);
          return next;
        });
      }
    },
    [mutateDraft],
  );

  /** 连线模式（＋子类）：给选中类点选父类 → parents 加边（批次 2 转正）。 */
  const [connectChild, setConnectChild] = useState<string | null>(null);
  useEffect(() => {
    if (!connectChild) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setConnectChild(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [connectChild]);

  const addParentEdge = useCallback(
    (child: string, parent: string) => {
      if (child === parent) {
        setSaveMsg("不能把类连到自己");
        return;
      }
      const ok = mutateDraft((obj) => {
        const classes = (obj.classes ?? {}) as Draft;
        const entry = (classes[child] ?? {}) as Draft;
        const parents = new Set([...((entry.parents as string[]) ?? []), parent]);
        classes[child] = { ...entry, parents: [...parents] };
        obj.classes = classes;
      });
      if (ok) setSaveMsg(`✓ 已连线 ${parent} → ${child}（subClassOf）——保存前须过校验`);
    },
    [mutateDraft],
  );

  const removeParentEdge = useCallback(
    (child: string, parent: string) => {
      const ok = mutateDraft((obj) => {
        const classes = (obj.classes ?? {}) as Draft;
        const entry = (classes[child] ?? {}) as Draft;
        classes[child] = {
          ...entry,
          parents: ((entry.parents as string[]) ?? []).filter((p) => p !== parent),
        };
        obj.classes = classes;
      });
      if (ok) setSaveMsg(`✓ 已移除连线 ${parent} → ${child}`);
    },
    [mutateDraft],
  );

  const handleNodeClick = (name: string) => {
    if (connectChild) {
      addParentEdge(connectChild, name);
      setConnectChild(null);
      return;
    }
    setSelectedClass(name);
  };

  const handleSave = useCallback(async () => {
    setBusy(true);
    try {
      const r = await saveRegistryContent(selectedFile, text);
      setSaveMsg(`✓ 已保存 v${r.registry_version}（SHA 热重载生效）`);
      setDraftText(null);
      await qc.invalidateQueries({ queryKey: ["registry-content", selectedFile] });
    } catch (e) {
      setSaveMsg(`✗ 保存失败: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  }, [selectedFile, text, qc]);

  const handleValidate = useCallback(async () => {
    setBusy(true);
    try {
      const r = await validateRegistryDraft(selectedFile, text);
      setSaveMsg(r.ok ? "✓ 校验通过（schema/引用/环）" : `✗ 校验失败: ${r.errors.join("; ")}`);
    } catch (e) {
      setSaveMsg(`✗ 校验请求失败: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  }, [selectedFile, text]);

  const yamlLineCount = useMemo(() => text.split("\n").length, [text]);

  const filesQuery = useQuery({
    queryKey: ["ontology", "registry-files"],
    queryFn: fetchRegistryFiles,
    staleTime: 5 * 60_000,
  });
  const files = filesQuery.data?.files ?? [];
  const contentQueries = useQueries({
    queries: files.map((file) => ({
      queryKey: ["registry-content", file],
      queryFn: () => fetchRegistryContent(file),
      staleTime: 5 * 60_000,
    })),
  });
  const contentCountFor = (file: string): number | undefined => {
    const idx = files.indexOf(file);
    const s = contentQueries[idx]?.data?.summary;
    if (!s) return undefined;
    const classes = s.domains?.[file.replace(/\.yaml$/, "")]?.classes;
    return classes ? (classes.length as number) : 0;
  };

  return (
    <div className="h-full overflow-x-auto overflow-y-auto">
      <div className="min-w-[1080px] p-6">
        <PageHeader
          icon={DraftingCompass}
          title="本体建模器"
          description="可视化建模（真实类层次画布：节点可拖拽移位、＋子类连线写 subClassOf、表单父类增删=边编辑）与 YAML 源码编辑同一 registry——画布是投影，编辑落为 YAML 差异。"
        />
        {saveMsg ? <SaveBanner msg={saveMsg} /> : null}
        {contentQuery.isLoading ? (
          <div className="text-muted-foreground py-16 text-center text-xs">
            <Loader2 className="mx-auto mb-2 h-4 w-4 animate-spin" />
            加载 registry…
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3.5 xl:grid-cols-[200px_minmax(0,1fr)_300px]">
            {/* 左栏：域文件列表 */}
            <div className="border-border bg-card rounded-xl border p-1.5 shadow-sm">
              {filesQuery.isLoading ? (
                <div className="text-muted-foreground p-2 text-xs">加载中…</div>
              ) : (
                files.map((file) => (
                  <FileTab
                    key={file}
                    name={file}
                    active={selectedFile === file}
                    classCount={contentCountFor(file)}
                    onClick={() => setSelectedFile(file)}
                  />
                ))
              )}
            </div>

            {/* 中：编辑器单面板 */}
            <div className="border-border bg-card rounded-xl border shadow-sm">
              <div className="border-border flex flex-wrap items-center gap-2 border-b px-4 py-2.5">
                <span className="font-mono text-xs">{selectedFile}</span>
                <div className="border-border ml-1 flex overflow-hidden rounded-lg border">
                  <button
                    type="button"
                    onClick={() => setMode("vis")}
                    className={cn(
                      "px-2.5 py-1 text-xs font-medium",
                      mode === "vis"
                        ? "bg-primary/10 text-primary font-semibold"
                        : "bg-card text-muted-foreground hover:bg-accent",
                    )}
                  >
                    可视化建模
                  </button>
                  <button
                    type="button"
                    onClick={() => setMode("yaml")}
                    className={cn(
                      "px-2.5 py-1 text-xs font-medium",
                      mode === "yaml"
                        ? "bg-primary/10 text-primary font-semibold"
                        : "bg-card text-muted-foreground hover:bg-accent",
                    )}
                  >
                    YAML 源码
                  </button>
                </div>
                {dirty ? (
                  <span className="bg-warning/15 text-warning rounded-full px-2 py-0.5 text-[11px] font-medium">
                    未保存
                  </span>
                ) : null}
                <div className="ml-auto flex items-center gap-2">
                  <span className="text-muted-foreground font-mono text-[10.5px]">
                    v{content?.registry_version ?? "—"} ·{" "}
                    {content?.fingerprint?.slice(0, 6) ?? "—"}
                  </span>
                  <button
                    type="button"
                    onClick={handleValidate}
                    disabled={busy || !text}
                    className="border-border bg-card hover:bg-muted rounded-md border px-2 py-1 text-xs font-medium disabled:opacity-50"
                  >
                    校验
                  </button>
                  <button
                    type="button"
                    onClick={handleSave}
                    disabled={busy || !text}
                    className="bg-primary text-primary-foreground hover:bg-primary/90 rounded-md px-2 py-1 text-xs font-medium disabled:opacity-50"
                  >
                    {busy ? <Loader2 className="mr-1 inline h-3 w-3 animate-spin" /> : null}
                    保存
                  </button>
                </div>
              </div>

              {mode === "vis" ? (
                <>
                  {/* 工具栏 */}
                  <div className="border-border flex flex-wrap items-center gap-2 border-b px-3.5 py-2.5">
                    <button
                      type="button"
                      onClick={addClass}
                      className="bg-primary text-primary-foreground hover:opacity-90 rounded-md px-2.5 py-1 text-xs font-medium"
                    >
                      ＋ 新建类
                    </button>
                    <button
                      type="button"
                      aria-pressed={connectChild !== null}
                      disabled={!selectedClass}
                      title={
                        selectedClass
                          ? `为 ${selectedClass} 连接父类：点击目标父类节点（Esc 取消）`
                          : "先选中一个子类"
                      }
                      onClick={() => setConnectChild(selectedClass)}
                      className={cn(
                        "rounded-md border px-2.5 py-1 text-xs font-medium disabled:opacity-40",
                        connectChild
                          ? "border-primary/50 bg-primary/10 text-primary"
                          : "border-border bg-card text-muted-foreground",
                      )}
                    >
                      ＋ 子类连线
                    </button>
                    <button
                      type="button"
                      disabled={!selectedClass}
                      onClick={() => removeClass(selectedClass as string)}
                      title="删除前先查引用（属性链/实例），确认后从草稿移除"
                      className="border-destructive/40 text-destructive rounded-md border px-2.5 py-1 text-xs disabled:opacity-40"
                    >
                      ✕ 删除
                    </button>
                    {connectChild ? (
                      <span className="bg-primary/10 text-primary animate-pulse rounded-full px-2.5 py-0.5 text-[11px] font-medium">
                        连线模式：为 {connectChild} 点击父类节点（Esc 取消）
                      </span>
                    ) : (
                      <span className="text-muted-foreground text-[10.5px]">
                        拖拽节点移位（视图态）· 连线写 subClassOf（结构数据）
                      </span>
                    )}
                  </div>
                  <TBoxCanvas
                    classes={allClasses}
                    positions={effectivePositions}
                    selected={selectedClass}
                    connectChild={connectChild}
                    instancesOf={instancesOf}
                    onNodeClick={handleNodeClick}
                    onNodeMove={(name, pos) =>
                      setPositionOverrides((prev) => {
                        const next = new Map(prev);
                        next.set(name, pos);
                        return next;
                      })
                    }
                    chains={axioms?.property_chains ?? []}
                    predicates={domainPredicates}
                  />
                </>
              ) : (
                <YamlEditor
                  text={text}
                  lineCount={yamlLineCount}
                  onChange={(v) => {
                    setDraftText(v);
                    setSaveMsg(null);
                  }}
                />
              )}
            </div>

            {/* 右栏 */}
            <div className="flex flex-col gap-3.5">
              <ClassDetailForm
                selected={selected}
                domainClasses={allClasses.map((c) => c.name)}
                onEdit={(field, value) =>
                  selected && editClassField(selected.name, field, value)
                }
                onAddParent={(parent) =>
                  selected && addParentEdge(selected.name, parent)
                }
                onRemoveParent={(parent) =>
                  selected && removeParentEdge(selected.name, parent)
                }
              />
              <AxiomsPanel axioms={axioms} predicates={domainPredicates} />
              <Panel title="校验面板" subtitle="保存前必须通过">
                <div className="p-4 text-xs">
                  <button
                    type="button"
                    onClick={handleValidate}
                    disabled={busy || !text}
                    className="border-border bg-card hover:bg-muted w-full rounded-md border px-2.5 py-1.5 font-medium disabled:opacity-50"
                  >
                    校验当前草稿
                  </button>
                  <p className="text-muted-foreground mt-2 text-[10.5px]">
                    检查 schema/引用/环。结果同时显示在顶部横幅。
                  </p>
                </div>
              </Panel>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── 子组件 ──

function SaveBanner({ msg }: { msg: string }) {
  const ok = msg.startsWith("✓");
  return (
    <div
      className={`${ok ? "bg-success/10 text-success" : "bg-destructive/10 text-destructive"} mb-3.5 rounded-lg border px-4 py-2.5 text-xs font-medium whitespace-pre-wrap`}
    >
      {msg}
    </div>
  );
}

function FileTab({
  name,
  active,
  classCount,
  onClick,
}: {
  name: string;
  active: boolean;
  classCount?: number;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "mb-0.5 flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-left font-mono text-xs transition-colors",
        active
          ? "bg-primary/10 text-primary font-semibold"
          : "text-muted-foreground hover:bg-accent hover:text-foreground",
      )}
    >
      <span className="truncate">{name}</span>
      {classCount !== undefined ? (
        <span className="text-muted-foreground ml-2 flex-none text-[10px]">
          {classCount} 类
        </span>
      ) : null}
    </button>
  );
}

function ClassDetailForm({
  selected,
  domainClasses,
  onEdit,
  onAddParent,
  onRemoveParent,
}: {
  selected: ClassEntry | null;
  domainClasses: string[];
  onEdit: (field: "label" | "definition", value: string) => void;
  onAddParent: (parent: string) => void;
  onRemoveParent: (parent: string) => void;
}) {
  if (!selected) {
    return (
      <Panel title="选中元素 · 类" actions={<Chip tone="primary">owl:Class</Chip>}>
        <div className="text-muted-foreground p-4 text-xs">
          ← 从画布中选择一个类开始编辑
        </div>
      </Panel>
    );
  }
  const addable = domainClasses.filter(
    (c) => c !== selected.name && !selected.parents.includes(c),
  );
  return (
    <Panel
      title={`选中元素 · ${selected.name}`}
      subtitle="可编辑：label / definition / 父类增删（=连线编辑）"
      actions={<Chip tone="primary">owl:Class</Chip>}
    >
      <div className="space-y-3 p-4">
        <label className="block">
          <span className="text-muted-foreground text-[11px] font-medium">
            名称（IRI 局部）
          </span>
          <input
            defaultValue={selected.name}
            key={`name-${selected.name}`}
            readOnly
            className="border-border bg-muted text-muted-foreground mt-1 h-8 w-full rounded-md border px-2.5 font-mono text-xs"
          />
        </label>
        <label className="block">
          <span className="text-muted-foreground text-[11px] font-medium">显示名 label</span>
          <input
            defaultValue={selected.label}
            key={`label-${selected.name}`}
            onBlur={(e) => {
              if (e.target.value !== selected.label) onEdit("label", e.target.value);
            }}
            className="border-input focus:border-primary mt-1 h-8 w-full rounded-md border px-2.5 text-xs outline-none"
          />
        </label>
        <label className="block">
          <span className="text-muted-foreground text-[11px] font-medium">定义 definition</span>
          <textarea
            defaultValue={selected.definition}
            key={`def-${selected.name}`}
            onBlur={(e) => {
              if (e.target.value !== selected.definition) onEdit("definition", e.target.value);
            }}
            rows={3}
            className="border-input focus:border-primary mt-1 w-full resize-y rounded-md border px-2.5 py-1.5 text-xs outline-none"
          />
        </label>
        {/* 父类 chips 可增删 = 画布连线编辑的数据面 */}
        <div>
          <span className="text-muted-foreground text-[11px] font-medium">
            父类 parents（✕ 移除 = 删连线）
          </span>
          <div className="border-border mt-1 flex min-h-8 flex-wrap items-center gap-1.5 rounded-md border px-2 py-1.5">
            {selected.parents.length === 0 ? (
              <span className="text-muted-foreground text-[11px]">—（无父类，根类）</span>
            ) : (
              selected.parents.map((p) => (
                <span
                  key={p}
                  className="border-primary/25 bg-primary/5 text-primary flex items-center gap-1 rounded-full border px-2 py-0.5 font-mono text-[10.5px]"
                >
                  {p}
                  <button
                    type="button"
                    aria-label={`移除父类 ${p}`}
                    onClick={() => onRemoveParent(p)}
                    className="opacity-60 hover:opacity-100"
                  >
                    ✕
                  </button>
                </span>
              ))
            )}
          </div>
          {addable.length > 0 ? (
            <select
              value=""
              onChange={(e) => {
                if (e.target.value) onAddParent(e.target.value);
              }}
              aria-label="添加父类"
              className="border-border bg-card text-muted-foreground mt-1 h-7 w-full rounded-md border px-2 text-xs"
            >
              <option value="">＋ 添加父类…</option>
              {addable.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          ) : null}
        </div>
        <ReadonlyChips title="键 hasKey" items={selected.hasKey} hint="结构编辑走 YAML 模式" />
        <ReadonlyChips title="实例类型 etypes" items={selected.etypes} hint="" />
      </div>
    </Panel>
  );
}

function ReadonlyChips({
  title,
  items,
  hint,
}: {
  title: string;
  items: string[];
  hint: string;
}) {
  return (
    <div>
      <span className="text-muted-foreground text-[11px] font-medium">{title}</span>
      <div className="border-border mt-1 flex min-h-8 flex-wrap items-center gap-1.5 rounded-md border px-2 py-1.5">
        {items.length === 0 ? (
          <span className="text-muted-foreground text-[11px]">—</span>
        ) : (
          items.map((item) => (
            <span
              key={item}
              className="border-primary/25 bg-primary/5 text-primary rounded-full border px-2 py-0.5 font-mono text-[10.5px]"
            >
              {item}
            </span>
          ))
        )}
      </div>
      {hint ? <span className="text-muted-foreground/70 mt-0.5 block text-[10px]">{hint}</span> : null}
    </div>
  );
}

function AxiomsPanel({
  axioms,
  predicates,
}: {
  axioms?: RegistryAxioms;
  predicates: string[];
}) {
  return (
    <Panel title="公理" subtitle="结构只读 · 编辑走 YAML 模式">
      <div className="space-y-3 p-4 text-xs">
        <div>
          <span className="text-muted-foreground text-[11px] font-medium">
            属性链 property_chains
          </span>
          <div className="mt-1 space-y-1">
            {(axioms?.property_chains ?? []).map((chain) => (
              <div
                key={chain.derived}
                className="border-primary/20 bg-primary/5 rounded-md border px-2.5 py-1.5 font-mono text-[11px]"
              >
                {chain.chain.join(" ∘ ")} ⇒ <b>{chain.derived}</b>
              </div>
            ))}
            {(axioms?.property_chains ?? []).length === 0 ? (
              <span className="text-muted-foreground text-[11px]">—</span>
            ) : null}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <ReadonlyChips title="传递 transitive" items={axioms?.transitive ?? []} hint="" />
          <ReadonlyChips
            title="不相交 disjoint"
            items={(axioms?.disjoint ?? []).map((d) => `[${d}]`)}
            hint=""
          />
        </div>
        <div>
          <span className="text-muted-foreground text-[11px] font-medium">逆 inverse</span>
          <div className="border-border mt-1 min-h-8 rounded-md border px-2 py-1.5 font-mono text-[10.5px]">
            {(axioms?.inverse ?? []).length === 0
              ? "—"
              : (axioms?.inverse ?? [])
                  .map((inv) => inv.pair.join(" ↔ "))
                  .join("；")}
          </div>
        </div>
      </div>
    </Panel>
  );
}

/** YAML 行号编辑器：行号列与编辑区同步滚动。 */
function YamlEditor({
  text,
  lineCount,
  onChange,
}: {
  text: string;
  lineCount: number;
  onChange: (v: string) => void;
}) {
  const gutterRef = useRef<HTMLDivElement | null>(null);
  const onScroll = (e: React.UIEvent<HTMLTextAreaElement>) => {
    if (gutterRef.current) {
      gutterRef.current.scrollTop = e.currentTarget.scrollTop;
    }
  };
  return (
    <div className="bg-code text-code-fg flex h-[560px] overflow-hidden">
      <div
        ref={gutterRef}
        className="text-muted-foreground/60 w-12 flex-none overflow-hidden border-r px-2 py-3 text-right font-mono text-[11.5px] leading-relaxed select-none"
      >
        {Array.from({ length: lineCount }, (_, i) => (
          <div key={i}>{i + 1}</div>
        ))}
      </div>
      <textarea
        value={text}
        onChange={(e) => onChange(e.target.value)}
        onScroll={onScroll}
        spellCheck={false}
        className="min-w-0 flex-1 resize-none p-3 font-mono text-[11.5px] leading-relaxed outline-none"
      />
    </div>
  );
}

/** TBox 画布：节点可拖拽移位（视图态）、连线模式点选父类、实例计数、谓词条、属性链。 */
function TBoxCanvas({
  classes,
  positions,
  selected,
  connectChild,
  instancesOf,
  onNodeClick,
  onNodeMove,
  chains,
  predicates,
}: {
  classes: ClassEntry[];
  positions: Map<string, Pos>;
  selected: string | null;
  connectChild: string | null;
  instancesOf: (cls: ClassEntry) => number | null;
  onNodeClick: (name: string) => void;
  onNodeMove: (name: string, pos: Pos) => void;
  chains: RegistryAxioms["property_chains"];
  predicates: string[];
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<{
    name: string;
    startX: number;
    startY: number;
    orig: Pos;
    moved: boolean;
  } | null>(null);

  const nodes = classes
    .filter((c) => positions.has(c.name))
    .map((c) => ({ cls: c, pos: positions.get(c.name) as Pos }));

  const onNodePointerDown = (
    e: React.PointerEvent<HTMLDivElement>,
    name: string,
  ) => {
    if (connectChild) return; // 连线模式点击走 click
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const orig = positions.get(name) ?? { x: 50, y: 50 };
    dragRef.current = { name, startX: e.clientX, startY: e.clientY, orig, moved: false };
    e.currentTarget.setPointerCapture(e.pointerId);
  };

  const onNodePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    const rect = containerRef.current?.getBoundingClientRect();
    if (!drag || !rect) return;
    const dxPct = ((e.clientX - drag.startX) / rect.width) * 100;
    const dyPct = ((e.clientY - drag.startY) / rect.height) * 100;
    if (!drag.moved && Math.hypot(dxPct, dyPct) < 1) return; // 死区：区分点击
    drag.moved = true;
    const x = Math.min(96, Math.max(4, drag.orig.x + dxPct));
    const y = Math.min(94, Math.max(6, drag.orig.y + dyPct));
    onNodeMove(drag.name, { x, y });
  };

  const onNodePointerUp = () => {
    dragRef.current = null;
  };

  const edges = useMemo(() => {
    const list: Array<{ key: string; parent: string; child: string; x1: number; y1: number; x2: number; y2: number }> = [];
    for (const cls of classes) {
      for (const p of cls.parents) {
        const a = positions.get(p);
        const b = positions.get(cls.name);
        if (a && b) {
          list.push({
            key: `${p}-${cls.name}`,
            parent: p,
            child: cls.name,
            x1: a.x,
            y1: a.y,
            x2: b.x,
            y2: b.y,
          });
        }
      }
    }
    return list;
  }, [classes, positions]);

  return (
    <div className="flex flex-col gap-2">
      <div
        ref={containerRef}
        className="relative h-[440px] overflow-hidden"
        style={{
          background:
            "radial-gradient(circle at 1px 1px, var(--border) 1px, transparent 0) 0 0 / 22px 22px, #fcfdfd",
        }}
        data-testid="tbox-canvas"
      >
        <svg
          className="pointer-events-none absolute inset-0 h-full w-full"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
        >
          {edges.map((edge) => {
            const isPending = connectChild === edge.child;
            return (
              <line
                key={edge.key}
                x1={edge.x1}
                y1={edge.y1}
                x2={edge.x2}
                y2={edge.y2}
                stroke={isPending ? withAlpha(AMBER, 0.7) : withAlpha(TONE_BLUE, 0.35)}
                strokeWidth={1.5}
                vectorEffect="non-scaling-stroke"
              />
            );
          })}
        </svg>
        {nodes.map(({ cls, pos }) => {
          const pos2 = pos ?? { x: 50, y: 50 };
          const count = instancesOf(cls);
          const isSel = selected === cls.name;
          const isPending = connectChild === cls.name;
          return (
            <div
              key={cls.name}
              role="button"
              tabIndex={0}
              onPointerDown={(e) => onNodePointerDown(e, cls.name)}
              onPointerMove={onNodePointerMove}
              onPointerUp={onNodePointerUp}
              onClick={() => onNodeClick(cls.name)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") onNodeClick(cls.name);
              }}
              className={cn(
                "absolute -translate-x-1/2 -translate-y-1/2 select-none text-center transition-transform",
                !dragRef.current && "hover:scale-105",
                connectChild && isPending ? "ring-primary ring-2" : "",
              )}
              style={{
                left: `${pos2.x}%`,
                top: `${pos2.y}%`,
                cursor: connectChild ? "crosshair" : "grab",
              }}
              data-testid={`tbox-node-${cls.name}`}
            >
              <span
                className={cn(
                  "block min-w-14 rounded-[10px] border-2 px-2.5 py-1.5 text-xs font-semibold shadow-sm",
                  isSel || isPending ? "text-white" : "text-foreground",
                )}
                style={{
                  background: isPending
                    ? withAlpha(AMBER, 0.9)
                    : isSel
                      ? TONE_BLUE
                      : "#fff",
                  borderColor: isPending
                    ? AMBER
                    : isSel
                      ? TONE_BLUE
                      : withAlpha(TONE_BLUE, 0.6),
                }}
              >
                {cls.name}
                <small
                  className={cn(
                    "block text-[10px] font-normal",
                    isSel || isPending ? "text-white/75" : "text-muted-foreground",
                  )}
                >
                  {cls.label || cls.name}
                </small>
              </span>
              {(() => {
                const c = count ?? undefined;
                return c !== undefined ? (
                  <span className="text-muted-foreground mt-0.5 block text-[10px] tabular-nums">
                    {c} 实例
                  </span>
                ) : null;
              })()}
            </div>
          );
        })}
        {connectChild ? (
          <div className="border-primary/40 bg-primary/10 text-primary absolute inset-x-3 top-3 z-10 rounded-md border px-3 py-1.5 text-[11px] font-medium">
            连线模式：点击目标父类节点（Esc 取消）
          </div>
        ) : null}
      </div>
      {connectChild ? null : (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-muted-foreground text-[10.5px] font-medium">谓词：</span>
          {predicates.length === 0 ? (
            <span className="text-muted-foreground text-[10.5px]">—</span>
          ) : (
            predicates.map((p) => (
              <span
                key={p}
                className="border-primary/25 bg-primary/5 text-primary rounded-full border px-2 py-0.5 font-mono text-[10px]"
              >
                {p}
              </span>
            ))
          )}
        </div>
      )}
      <div className="flex flex-col gap-1.5">
        {chains.length === 0 ? (
          <span className="text-muted-foreground text-[10.5px]">本域无属性链公理</span>
        ) : (
          chains.map((chain) => (
            <div
              key={chain.derived}
              className="border-primary/25 bg-primary/5 text-primary rounded-lg border border-dashed px-2.5 py-1.5 font-mono text-[11px]"
            >
              {chain.chain.join(" ∘ ")} ⇒ <b>{chain.derived}</b>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
