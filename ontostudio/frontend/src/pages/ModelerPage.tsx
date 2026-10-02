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
import { DraftingCompass, Loader2, Maximize2, Minimize2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { yaml } from "@codemirror/lang-yaml";
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
import { fetchPredicateLabels } from "@/explorerDataSource";
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
/** stage 逻辑高度（px）：节点位置是 stage 高度的百分比，缩放换算依赖此常量。 */
const STAGE_H = 440;

export function ModelerPage({ initialFile }: { initialFile?: string }) {
  const qc = useQueryClient();
  const [selectedFile, setSelectedFile] = useState(initialFile ?? "doc_graph.yaml");
  const [selectedClass, setSelectedClass] = useState<string | null>(null);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [mode, setMode] = useState<"vis" | "yaml">("vis");
  // 编辑面板最大化（2026-10-02 用户要求）：fixed 覆盖视口，画布随之加高
  const [maximized, setMaximized] = useState(false);
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

  // 节点位置持久化（localStorage 按域文件分键；刷新保持，域切换加载对应位置）
  const loadSavedPositions = useCallback((file: string): Map<string, Pos> => {
    try {
      const raw = localStorage.getItem(`ontostudio-canvas-pos-${file}`);
      if (!raw) return new Map();
      const obj = JSON.parse(raw) as Record<string, Pos>;
      return new Map(Object.entries(obj));
    } catch {
      return new Map();
    }
  }, []);
  const persistPositions = useCallback(
    (file: string, overrides: Map<string, Pos>) => {
      try {
        const obj: Record<string, Pos> = {};
        overrides.forEach((pos, name) => {
          obj[name] = pos;
        });
        localStorage.setItem(
          `ontostudio-canvas-pos-${file}`,
          JSON.stringify(obj),
        );
      } catch {
        /* 存储满/隐私模式忽略 */
      }
    },
    [],
  );

  const [positionOverrides, setPositionOverrides] = useState<Map<string, Pos>>(
    () => loadSavedPositions(selectedFile),
  );
  const persistRef = useRef(persistPositions);
  persistRef.current = persistPositions;

  useEffect(() => {
    setDraftText(null);
    setSelectedClass(null);
    setConnectChild(null);
    setPositionOverrides(loadSavedPositions(selectedFile));
  }, [selectedFile]); // 仅域切换时重置（YAML 热重载不清位置——用户手动调整不丢）

  const remoteText = content?.raw ?? "";
  const text = draftText ?? remoteText;
  const dirty = draftText !== null && draftText !== remoteText;

  // 类数据来源：domainSummary（服務端 API 已解析 registry YAML 為結構化數據）——
  // 正確處理 eia.yaml 的 etype_classes 嵌套結構和 doc_graph.yaml 的 classes 結構
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

  // P1 谓词区补齐（2026-10-02 CEO 审核项）：中文标注（YAML 注释块解析，同 etypeLabels 先例）
  // + 使用计数。谓词枚举按域互斥（eia/doc_graph 不相交），全局 predicate 聚合 ∩ 本域枚举
  // 即本域计数——graph_relation 无 domain 列，这是零后端改动的正确口径；与总览页共享缓存 key。
  const predicateLabelsQuery = useQuery({
    queryKey: ["ontology", "predicate-labels", selectedFile],
    queryFn: () => fetchPredicateLabels(selectedFile),
    enabled: domainPredicates.length > 0,
    staleTime: Number.POSITIVE_INFINITY,
  });
  const predicateCountQuery = useQuery({
    queryKey: ["ontology", "aggregate", "graph_relation", "predicate"],
    queryFn: ({ signal }) => fetchAggregate("graph_relation", "predicate", { signal }),
    enabled: domainPredicates.length > 0,
    staleTime: 60_000,
  });
  const countByPredicate = useMemo(() => {
    const map = new Map<string, number>();
    for (const row of predicateCountQuery.data ?? []) {
      if (row.group) map.set(row.group, row.value);
    }
    return map;
  }, [predicateCountQuery.data]);

  // 基础布局（继承深度分层 + 网格防重叠）；用户拖拽写 overrides，读时覆盖
  const baseLayout = useMemo(() => {
    const layers = new Map<number, ClassEntry[]>();
    for (const { cls, depth } of buildTree(allClasses)) {
      const list = layers.get(depth) ?? [];
      list.push(cls);
      layers.set(depth, list);
    }
    const sortedDepths = [...layers.keys()].sort((a, b) => a - b);
    const positions = new Map<string, Pos>();

    // 布局参数：每层节点最多 6 个一行，超出换子行；层间距 ≥ 20%
    const MAX_PER_ROW = 6;
    const X_START = 8;
    const X_SLOT = 14; // 每节点最小占 14% 宽度
    const Y_START = 10;
    const Y_SLOT = 20; // 每层最小占 20% 高度

    let visualRow = 0;
    for (const depth of sortedDepths) {
      const row = layers.get(depth) ?? [];
      const subRows = Math.ceil(row.length / MAX_PER_ROW);
      for (let sr = 0; sr < subRows; sr++) {
        const slice = row.slice(sr * MAX_PER_ROW, (sr + 1) * MAX_PER_ROW);
        const n = slice.length;
        slice.forEach((cls, i) => {
          positions.set(cls.name, {
            x: X_START + ((i + 0.5) * (100 - 2 * X_START)) / n,
            y: Y_START + visualRow * Y_SLOT,
          });
        });
        visualRow++;
      }
    }
    return positions;
  }, [allClasses]);

  // 草稿预览边（v4）：从草稿 YAML 解析 subClassOf 关系，保存前画布即见新边
  // （琥珀虚线=未保存；保存后转实线蓝）。YAML 非法时回退空。
  const draftEdges = useMemo(() => {
    try {
      const obj = yamlLoad(text) as Draft;
      const classes = (obj.classes ?? {}) as Draft;
      const list: Array<{ key: string; parent: string; child: string }> = [];
      for (const [child, entry] of Object.entries(classes) as Array<[string, Draft]>) {
        for (const p of ((entry.parents as string[]) ?? [])) {
          list.push({ key: `${p}-${child}`, parent: p, child });
        }
      }
      return list;
    } catch {
      return [];
    }
  }, [text]);

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
        // 联动清理：子类的 parents 引用同步摘除（否则幽灵父类留到保存后，
        // 子类芯片与画布边持续引用已删类；v4 审计 M1）
        for (const [name, entry] of Object.entries(classes) as Array<[string, Draft]>) {
          const parents = ((entry as Draft).parents as string[]) ?? [];
          if (parents.includes(clsName)) {
            classes[name] = { ...entry, parents: parents.filter((p) => p !== clsName) };
          }
        }
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

  const handleNodeMove = useCallback(
    (name: string, pos: Pos) => {
      setPositionOverrides((prev) => {
        const next = new Map(prev);
        next.set(name, pos);
        try {
          const obj: Record<string, Pos> = {};
          next.forEach((p, n) => {
            obj[n] = p;
          });
          localStorage.setItem(
            `ontostudio-canvas-pos-${selectedFile}`,
            JSON.stringify(obj),
          );
        } catch {
          /* ignore */
        }
        return next;
      });
    },
    [selectedFile],
  );

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
          <div className="text-muted-foreground py-16 text-center text-sm">
            <Loader2 className="mx-auto mb-2 h-4 w-4 animate-spin" />
            加载 registry…
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3.5 xl:grid-cols-[200px_minmax(0,1fr)_300px]">
            {/* 左栏：域文件列表 */}
            <div className="border-border bg-card rounded-xl border p-1.5 shadow-sm">
              {filesQuery.isLoading ? (
                <div className="text-muted-foreground p-2 text-sm">加载中…</div>
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

            {/* 中：编辑器面板（可最大化）+ 谓词与公理独立面板（画布下方不堆叠行——遮挡节点） */}
            <div className="flex flex-col gap-3.5">
            <div className={cn(
              "border-border bg-card border shadow-sm",
              maximized ? "fixed inset-4 z-50 overflow-auto rounded-xl bg-background" : "rounded-xl",
            )}>
              <div className="border-border flex flex-wrap items-center gap-2 border-b px-4 py-2.5">
                <span className="font-mono text-sm">{selectedFile}</span>
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
                  <span className="bg-warning/15 text-warning rounded-full px-2 py-0.5 text-xs font-medium">
                    未保存
                  </span>
                ) : null}
                <div className="ml-auto flex items-center gap-2">
                  <span className="text-muted-foreground font-mono text-xs">
                    v{content?.registry_version ?? "—"} ·{" "}
                    {content?.fingerprint?.slice(0, 6) ?? "—"}
                  </span>
                  <button
                    type="button"
                    onClick={handleValidate}
                    disabled={busy || !text}
                    className="border-border bg-card hover:bg-muted rounded-sm border px-2 py-1 text-sm font-medium disabled:opacity-50"
                  >
                    校验
                  </button>
                  <button
                    type="button"
                    onClick={handleSave}
                    disabled={busy || !text}
                    className="bg-primary text-primary-foreground hover:bg-primary/90 rounded-sm px-2 py-1 text-sm font-medium disabled:opacity-50"
                  >
                    {busy ? <Loader2 className="mr-1 inline h-3 w-3 animate-spin" /> : null}
                    保存
                  </button>
                  <button
                    type="button"
                    onClick={() => setMaximized((m) => !m)}
                    title={maximized ? "还原面板" : "最大化编辑面板"}
                    aria-label={maximized ? "还原面板" : "最大化编辑面板"}
                    className="border-border bg-card hover:bg-muted rounded-sm border px-2 py-1 text-sm disabled:opacity-50"
                  >
                    {maximized ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
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
                      className="bg-primary text-primary-foreground hover:opacity-90 rounded-sm px-2.5 py-1 text-xs font-medium"
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
                        "rounded-sm border px-2.5 py-1 text-xs font-medium disabled:opacity-40",
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
                      className="border-destructive/40 text-destructive rounded-sm border px-2.5 py-1 text-xs disabled:opacity-40"
                    >
                      ✕ 删除
                    </button>
                    {connectChild ? (
                      <span className="bg-primary/10 text-primary animate-pulse rounded-full px-2.5 py-0.5 text-xs font-medium">
                        连线模式：为 {connectChild} 点击父类节点（Esc 取消）
                      </span>
                    ) : (
                      <span className="text-muted-foreground text-xs">
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
                    onNodeMove={handleNodeMove}
                    draftEdges={draftEdges}
                    heightClass={maximized ? "h-[calc(100vh-230px)]" : "h-[440px]"}
                  />
                </>
              ) : (
                <YamlEditor
                  text={text}
                  onChange={(v) => {
                    setDraftText(v);
                    setSaveMsg(null);
                  }}
                />
              )}
            </div>

            {/* 谓词与公理独立面板（2026-10-02 用户纠正：不放画布下方）；最大化时隐藏 */}
            {!maximized ? (
              <PredicateAxiomPanel
                predicates={domainPredicates}
                counts={countByPredicate}
                labels={predicateLabelsQuery.data}
                axioms={axioms}
              />
            ) : null}
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
                onAddEtype={(et) => {
                  if (!selected) return;
                  mutateDraft((obj) => {
                    const classes = (obj.classes ?? {}) as Draft;
                    const entry = (classes[selected.name] ?? {}) as Draft;
                    const etypes = new Set([...((entry.etypes as string[]) ?? []), et]);
                    classes[selected.name] = { ...entry, etypes: [...etypes] };
                    obj.classes = classes;
                  });
                }}
                onRemoveEtype={(et) => {
                  if (!selected) return;
                  mutateDraft((obj) => {
                    const classes = (obj.classes ?? {}) as Draft;
                    const entry = (classes[selected.name] ?? {}) as Draft;
                    classes[selected.name] = {
                      ...entry,
                      etypes: ((entry.etypes as string[]) ?? []).filter((e) => e !== et),
                    };
                    obj.classes = classes;
                  });
                }}
              />
              <AxiomsPanel axioms={axioms} predicates={domainPredicates} />
              <Panel title="校验面板" subtitle="保存前必须通过">
                <div className="p-4 text-sm">
                  <button
                    type="button"
                    onClick={handleValidate}
                    disabled={busy || !text}
                    className="border-border bg-card hover:bg-muted w-full rounded-md border px-2.5 py-1.5 font-medium disabled:opacity-50"
                  >
                    校验当前草稿
                  </button>
                  <p className="text-muted-foreground mt-2 text-xs">
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
      className={`${ok ? "bg-success/10 text-success" : "bg-destructive/10 text-destructive"} mb-3.5 rounded-lg border px-4 py-2.5 text-sm font-medium whitespace-pre-wrap`}
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
        "mb-0.5 flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-left font-mono text-sm transition-colors",
        active
          ? "bg-primary/10 text-primary font-semibold"
          : "text-muted-foreground hover:bg-accent hover:text-foreground",
      )}
    >
      <span className="truncate">{name}</span>
      {classCount !== undefined ? (
        <span className="text-muted-foreground ml-2 flex-none text-[13px]">
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
  onAddEtype,
  onRemoveEtype,
}: {
  selected: ClassEntry | null;
  domainClasses: string[];
  onEdit: (field: "label" | "definition", value: string) => void;
  onAddParent: (parent: string) => void;
  onRemoveParent: (parent: string) => void;
  onAddEtype: (et: string) => void;
  onRemoveEtype: (et: string) => void;
}) {
  // 本地 parents 狀態：初始化自 selected，操作即時更新 UI，
  // 同時通過 onAddParent/onRemoveParent 同步到草稿管線。
  // v4 修复冻结 bug：useState 初始值只在首挂生效——切换选中类必须显式同步，
  // 否则芯片停留在第一个选中类的父类（v4 审计实证）。
  const [localParents, setLocalParents] = useState<string[]>(
    selected ? [...selected.parents] : [],
  );
  useEffect(() => {
    setLocalParents(selected ? [...selected.parents] : []);
  }, [selected?.name]);

  // etypes 本地态（v4 接线死 props：onAddEtype/onRemoveEtype 原本无 UI 调用点）
  const [localEtypes, setLocalEtypes] = useState<string[]>(
    selected ? [...selected.etypes] : [],
  );
  useEffect(() => {
    setLocalEtypes(selected ? [...selected.etypes] : []);
  }, [selected?.name]);

  // 父类 Combobox 状态
  const [parentQuery, setParentQuery] = useState("");
  const [etypeInput, setEtypeInput] = useState("");
  const [parentOpen, setParentOpen] = useState(false);
  const parentBoxRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!parentOpen) return;
    const onDocMouseDown = (e: MouseEvent) => {
      if (parentBoxRef.current && !parentBoxRef.current.contains(e.target as Node)) {
        setParentOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocMouseDown);
    return () => document.removeEventListener("mousedown", onDocMouseDown);
  }, [parentOpen]);
  const addParentLocal = (p: string) => {
    if (!p || localParents.includes(p)) return;
    setLocalParents((prev) => [...prev, p]);
    onAddParent(p);
  };
  const removeParentLocal = (p: string) => {
    setLocalParents((prev) => prev.filter((x) => x !== p));
    onRemoveParent(p);
  };
  const addEtypeLocal = (et: string) => {
    const et2 = et.trim();
    if (!et2 || localEtypes.includes(et2)) return;
    setLocalEtypes((prev) => [...prev, et2]);
    onAddEtype(et2);
  };
  const removeEtypeLocal = (et: string) => {
    setLocalEtypes((prev) => prev.filter((x) => x !== et));
    onRemoveEtype(et);
  };
  const parentCandidates = domainClasses.filter(
    (c) => !localParents.includes(c) &&
      (!parentQuery || c.toLowerCase().includes(parentQuery.toLowerCase())),
  );

  if (!selected) {
    return (
      <div className="border-border bg-card rounded-xl border shadow-sm">
        <div className="border-border flex items-center gap-2 border-b px-4 py-3">
          <b className="text-sm font-semibold">选中元素 · 类</b>
        </div>
        <div className="text-muted-foreground p-4 text-sm">
          ← 从画布中选择一个类开始编辑
        </div>
      </div>
    );
  }
  return (
    <div className="border-border bg-card rounded-xl border shadow-sm">
      {/* 标题栏 */}
      <div className="border-border flex items-center gap-2 border-b px-4 py-3">
        <b className="text-sm font-semibold">选中元素 · {selected.name}</b>
        <Chip tone="primary">owl:Class</Chip>
      </div>
      <div className="space-y-4 px-4 py-3 text-sm">
        {/* 基础信息 */}
        <fieldset>
          <legend className="text-primary mb-2 text-xs font-semibold tracking-wide">◆ 基础信息</legend>
          <div className="space-y-2.5">
            <label className="block">
              <span className="text-muted-foreground text-xs">名称（IRI 局部）</span>
              <input
                defaultValue={selected.name}
                key={`name-${selected.name}`}
                readOnly
                className="border-border bg-muted text-muted-foreground mt-0.5 h-7 w-full rounded-md border px-2 font-mono text-sm"
              />
            </label>
            <label className="block">
              <span className="text-muted-foreground text-xs">显示名 label</span>
              <input
                defaultValue={selected.label}
                key={`label-${selected.name}`}
                onBlur={(e) => {
                  if (e.target.value !== selected.label) onEdit("label", e.target.value);
                }}
                className="border-input focus:border-primary mt-0.5 h-7 w-full rounded-md border px-2 text-sm outline-none"
              />
            </label>
            <label className="block">
              <span className="text-muted-foreground text-xs">定义 definition</span>
              <textarea
                defaultValue={selected.definition}
                key={`def-${selected.name}`}
                onBlur={(e) => {
                  if (e.target.value !== selected.definition) onEdit("definition", e.target.value);
                }}
                rows={3}
                className="border-input focus:border-primary mt-0.5 w-full resize-y rounded-md border px-2 py-1.5 text-sm outline-none"
              />
            </label>
          </div>
        </fieldset>
        {/* 继承关系 */}
        <fieldset>
          <legend className="text-primary mb-2 text-xs font-semibold tracking-wide">◆ 继承关系</legend>
          <div>
            <span className="text-muted-foreground text-xs">父类 parents</span>
            <div className="relative mt-1" ref={parentBoxRef}>
              <input
                value={parentQuery}
                onChange={(e) => {
                  setParentQuery(e.target.value);
                  setParentOpen(true);
                }}
                onFocus={() => setParentOpen(true)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && parentCandidates.length > 0) {
                    const first = parentCandidates[0];
                    if (first) addParentLocal(first);
                    setParentQuery("");
                    setParentOpen(false);
                  }
                  if (e.key === "Escape") setParentOpen(false);
                }}
                placeholder="输入筛选父类（类名）…"
                aria-label="添加父类"
                className="border-input focus:border-primary h-7 w-full rounded-md border px-2 text-sm outline-none"
              />
              {parentOpen ? (
                <div className="border-border absolute z-10 mt-0.5 max-h-44 w-full overflow-y-auto rounded-md border bg-card shadow-md">
                  {parentCandidates.length === 0 ? (
                    <div className="text-muted-foreground px-2 py-1.5 text-xs">无可添加的父类（已全部选中）</div>
                  ) : (
                    parentCandidates.map((c) => (
                      <button
                        key={c}
                        type="button"
                        onClick={() => {
                          addParentLocal(c);
                          setParentQuery("");
                          setParentOpen(false);
                        }}
                        className="hover:bg-primary-soft block w-full px-2.5 py-1 text-left text-xs"
                      >
                        {c}
                      </button>
                    ))
                  )}
                </div>
              ) : null}
            </div>
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
              {localParents.length === 0 ? (
                <span className="text-muted-foreground text-xs">—（根类）</span>
              ) : (
                localParents.map((p) => (
                  <span
                    key={p}
                    className="border-primary/25 bg-primary/5 text-primary flex items-center gap-1 rounded-full border px-2.5 py-0.5 font-mono text-xs"
                  >
                    {p}
                    <button
                      type="button"
                      aria-label={`移除父类 ${p}`}
                      onClick={() => removeParentLocal(p)}
                      className="opacity-60 hover:opacity-100"
                    >
                      ✕
                    </button>
                  </span>
                ))
              )}
            </div>
          </div>
        </fieldset>
        {/* 类型标注 */}
        <fieldset>
          <legend className="text-primary mb-2 text-xs font-semibold tracking-wide">类型标注</legend>
          <label className="block">
            <span className="text-muted-foreground text-xs">键 hasKey</span>
            <input
              defaultValue={selected.hasKey.join(", ")}
              key={`key-${selected.name}`}
              readOnly
              placeholder="如 name"
              className="border-border bg-muted text-muted-foreground mt-0.5 h-7 w-full rounded-md border px-2 font-mono text-sm"
            />
          </label>
          <div className="mt-2">
            <span className="text-muted-foreground text-xs">实例类型 etypes</span>
            <div className="mt-1 flex flex-wrap items-center gap-1.5">
              {localEtypes.length === 0 ? (
                <span className="text-muted-foreground text-xs">—</span>
              ) : (
                localEtypes.map((et) => (
                  <span
                    key={et}
                    className="inline-flex items-center gap-1 rounded-full border border-primary/25 bg-primary/5 px-2.5 py-0.5 font-mono text-xs text-primary"
                  >
                    {et}
                    <button
                      type="button"
                      aria-label={`移除实例类型 ${et}`}
                      onClick={() => removeEtypeLocal(et)}
                      className="opacity-60 hover:opacity-100"
                    >
                      ✕
                    </button>
                  </span>
                ))
              )}
              <input
                value={etypeInput}
                onChange={(e) => setEtypeInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") addEtypeLocal(etypeInput);
                }}
                placeholder="＋ 输入 etype 后回车"
                aria-label="添加实例类型"
                className="border-input focus:border-primary h-6 w-32 rounded-md border px-1.5 font-mono text-xs outline-none"
              />
            </div>
            <span className="text-muted-foreground/60 mt-1 block text-xs">
              由 registry etype_class_map 派生；Enter 添加，✕ 移除（写草稿 etypes 数组）
            </span>
          </div>
        </fieldset>
      </div>
    </div>
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
      <span className="text-muted-foreground text-xs font-medium">{title}</span>
      <div className="border-border mt-1 flex min-h-8 flex-wrap items-center gap-1.5 rounded-md border px-2 py-1.5">
        {items.length === 0 ? (
          <span className="text-muted-foreground text-xs">—</span>
        ) : (
          items.map((item) => (
            <span
              key={item}
              className="border-primary/25 bg-primary/5 text-primary rounded-full border px-2 py-0.5 font-mono text-xs"
            >
              {item}
            </span>
          ))
        )}
      </div>
      {hint ? <span className="text-muted-foreground/70 mt-0.5 block text-xs">{hint}</span> : null}
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
    <Panel title="公理" subtitle="本域自动派生规则全集 · 结构只读 · 编辑走 YAML 模式">
      <div className="space-y-3 p-4 text-sm">
        <div>
          <span className="text-muted-foreground text-xs font-medium">
            属性链 property_chains
          </span>
          <div className="mt-1 space-y-1">
            {(axioms?.property_chains ?? []).map((chain) => (
              <div
                key={chain.derived}
                className="border-primary/20 bg-primary/5 rounded-md border px-2.5 py-1.5 font-mono text-xs"
              >
                {chain.chain.join(" ∘ ")} ⇒ <b>{chain.derived}</b>
              </div>
            ))}
            {(axioms?.property_chains ?? []).length === 0 ? (
              <span className="text-muted-foreground text-xs">—</span>
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
          <span className="text-muted-foreground text-xs font-medium">逆 inverse</span>
          <div className="border-border mt-1 min-h-8 rounded-md border px-2 py-1.5 font-mono text-xs">
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

/** YAML 行号编辑器（CodeMirror 6：语法高亮 + 行号 + 自动缩进 + 括号匹配）。 */
function YamlEditor({
  text,
  onChange,
}: {
  text: string;
  onChange: (v: string) => void;
}) {
  return (
    <CodeMirror
      value={text}
      height="560px"
      theme="light"
      extensions={[yaml()]}
      onChange={onChange}
      basicSetup={{
        lineNumbers: true,
        foldGutter: true,
        highlightActiveLine: true,
        autocompletion: false,
      }}
      style={{ fontSize: "13px", fontFamily: "var(--font-mono, monospace)" }}
    />
  );
}

/** TBox 画布：节点可拖拽移位（视图态）、连线模式点选父类、实例计数、缩放工具栏。
 *  谓词/公理不在此渲染（用户纠正 2026-10-02：画布下方堆叠行遮挡下部节点）→ 独立 PredicateAxiomPanel。 */
function TBoxCanvas({
  classes,
  positions,
  selected,
  connectChild,
  instancesOf,
  onNodeClick,
  onNodeMove,
  draftEdges,
  heightClass = "h-[440px]",
}: {
  classes: ClassEntry[];
  positions: Map<string, Pos>;
  selected: string | null;
  connectChild: string | null;
  instancesOf: (cls: ClassEntry) => number | null;
  onNodeClick: (name: string) => void;
  onNodeMove: (name: string, pos: Pos) => void;
  draftEdges: Array<{ key: string; parent: string; child: string }>;
  /** 最大化模式下传更高的高度类。 */
  heightClass?: string;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [zoom, setZoom] = useState(1);
  // stage 高度实测跟随容器（最大化时容器=calc(100vh-230px)，固定 440 会让下半段成为
  // 节点拖不进去的死区——用户报告 2026-10-02）；位置是 stage 百分比，stage 铺满即全程可拖。
  const [stageH, setStageH] = useState(STAGE_H);
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setStageH(el.clientHeight));
    ro.observe(el);
    setStageH(el.clientHeight);
    return () => ro.disconnect();
  }, []);
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
    // 缩放下：屏幕位移换算回 stage 百分比——水平除以 stage 视觉宽（=容器宽×zoom），
    // 竖直除以 stage 视觉高（=stageH×zoom）。竖直误用容器宽会让下拖灵敏度虚低（bug 修复）。
    const dxPct = ((e.clientX - drag.startX) / (rect.width * zoom)) * 100;
    const dyPct = ((e.clientY - drag.startY) / (stageH * zoom)) * 100;
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
  }, [classes, positions, draftEdges]);

  // 合并：服务端 subClassOf 边（实线蓝）+ 仅草稿中的新边（虚线琥珀=未保存）
  const mergedEdges = useMemo(() => {
    const serverKeys = new Set(
      classes.flatMap((cls) => cls.parents.map((p) => `${p}-${cls.name}`)),
    );
    const list: Array<{ key: string; parent: string; child: string; x1: number; y1: number; x2: number; y2: number; draftOnly: boolean }> = [];
    for (const cls of classes) {
      for (const p of cls.parents) {
        const a = positions.get(p);
        const b = positions.get(cls.name);
        if (a && b) {
          list.push({
            key: `${p}-${cls.name}`,
            parent: p,
            child: cls.name,
            x1: a.x, y1: a.y, x2: b.x, y2: b.y,
            draftOnly: false,
          });
        }
      }
    }
    for (const de of draftEdges) {
      if (serverKeys.has(de.key)) continue;
      const a = positions.get(de.parent);
      const b = positions.get(de.child);
      if (a && b) {
        list.push({
          key: de.key,
          parent: de.parent,
          child: de.child,
          x1: a.x, y1: a.y, x2: b.x, y2: b.y,
          draftOnly: true,
        });
      }
    }
    return list;
  }, [classes, positions, draftEdges]);

  return (
    <div className="flex flex-col gap-2">
      <div
        ref={containerRef}
        className={cn("relative overflow-auto", heightClass)}
        style={{
          background:
            "radial-gradient(circle at 1px 1px, var(--border) 1px, transparent 0) 0 0 / 22px 22px, #fcfdfd",
        }}
        data-testid="tbox-canvas"
      >
        {/* 缩放工具栏（z 最高、不随缩放；stage 本体在 sizer 内等比缩放） */}
        <div className="border-border absolute right-2 top-2 z-20 flex items-center gap-0.5 rounded-md border bg-card/95 px-1 py-0.5 shadow-sm">
          <button
            type="button"
            onClick={() => setZoom((z) => Math.max(0.5, Number((z - 0.25).toFixed(2))))}
            title="缩小"
            aria-label="缩小画布"
            className="text-muted-foreground hover:text-foreground hover:bg-muted rounded px-1.5 py-0.5 text-sm font-bold"
          >
            －
          </button>
          <span className="text-muted-foreground w-10 text-center font-mono text-[10px] tabular-nums">
            {Math.round(zoom * 100)}%
          </span>
          <button
            type="button"
            onClick={() => setZoom((z) => Math.min(2.5, Number((z + 0.25).toFixed(2))))}
            title="放大"
            aria-label="放大画布"
            className="text-muted-foreground hover:text-foreground hover:bg-muted rounded px-1.5 py-0.5 text-sm font-bold"
          >
            ＋
          </button>
          <button
            type="button"
            onClick={() => setZoom(1)}
            title="重置缩放"
            className="text-muted-foreground hover:text-foreground hover:bg-muted rounded px-1.5 py-0.5 text-xs font-medium"
          >
            重置
          </button>
        </div>
        {/* sizer 撑出滚动范围；stage 原尺寸经 scale(zoom) 放大，节点/边随缩放 */}
        <div style={{ width: `${zoom * 100}%`, height: `${stageH * zoom}px` }}>
          <div
            className="relative origin-top-left"
            style={{ width: `${100 / zoom}%`, height: stageH, transform: `scale(${zoom})` }}
          >
        <svg
          className="pointer-events-none absolute inset-0 h-full w-full"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
        >
          {mergedEdges.map((edge) => {
            const isPending = connectChild === edge.child;
            return (
              <line
                key={edge.key}
                x1={edge.x1}
                y1={edge.y1}
                x2={edge.x2}
                y2={edge.y2}
                stroke={isPending ? withAlpha(AMBER, 0.7) : edge.draftOnly ? withAlpha(AMBER, 0.55) : withAlpha(TONE_BLUE, 0.35)}
                strokeWidth={1.5}
                strokeDasharray={edge.draftOnly ? "6 4" : undefined}
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
                  "block min-w-14 rounded-[10px] border-2 px-2.5 py-1.5 text-sm font-semibold shadow-sm",
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
                    "block text-xs font-normal",
                    isSel || isPending ? "text-white/75" : "text-muted-foreground",
                  )}
                >
                  {cls.label || cls.name}
                </small>
              </span>
              {(() => {
                const c = count ?? undefined;
                return c !== undefined ? (
                  <span className="text-muted-foreground mt-0.5 block text-xs tabular-nums">
                    {c} 实例
                  </span>
                ) : null;
              })()}
            </div>
          );
        })}
        {connectChild ? (
          <div className="border-primary/40 bg-primary/10 text-primary absolute inset-x-3 top-3 z-10 rounded-md border px-3 py-1.5 text-xs font-medium">
            连线模式：点击目标父类节点（Esc 取消）
          </div>
        ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

/** 画布下公理摘要行（A1，2026-10-02 CEO 审核）：只报数指路，避免与右栏「公理」面板双渲染。 */
function AxiomSummary({ axioms }: { axioms?: RegistryAxioms }) {
  if (!axioms) return null;
  const parts: string[] = [];
  if (axioms.property_chains.length > 0) parts.push(`属性链 ${axioms.property_chains.length} 条`);
  if (axioms.transitive.length > 0) parts.push(`传递 ${axioms.transitive.length} 项`);
  if (axioms.inverse.length > 0) parts.push(`逆 ${axioms.inverse.length} 对`);
  if (axioms.disjoint.length > 0) parts.push(`不相交 ${axioms.disjoint.length} 组`);
  return (
    <span className="text-muted-foreground text-xs">
      {parts.length > 0
        ? `自动派生规则：${parts.join(" · ")} → 详见右栏「公理」`
        : "本域暂无自动派生规则——如需跨关系推导，在 YAML 模式 axioms 块添加（property_chains / transitive / inverse）"}
    </span>
  );
}

/** 谓词与公理独立面板（2026-10-02 用户纠正：不堆叠画布下方遮挡节点）。
 *  谓词芯片 = 英文名 + 中文标注（YAML 注释块解析）+ 图中三元组计数；公理行报数指路。 */
function PredicateAxiomPanel({
  predicates,
  counts,
  labels,
  axioms,
}: {
  predicates: string[];
  counts: Map<string, number>;
  labels?: Map<string, string>;
  axioms?: RegistryAxioms;
}) {
  return (
    <Panel title="谓词与公理" subtitle="本域关系词汇使用情况与自动派生规则">
      <div className="flex flex-col gap-2.5 p-4">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-muted-foreground text-xs font-medium">谓词（关系类型）：</span>
          {predicates.length === 0 ? (
            <span className="text-muted-foreground text-xs">—</span>
          ) : (
            predicates.map((p) => {
              const label = labels?.get(p);
              const count = counts.get(p);
              return (
                <span
                  key={p}
                  className="border-primary/25 bg-primary/5 text-primary rounded-full border px-2 py-0.5 font-mono text-xs"
                  title={`本域定义的关系类型${label ? `：${label}` : ""}${
                    count !== undefined
                      ? `；图中该谓词 ${count.toLocaleString()} 条三元组${count === 0 ? "（已定义未使用）" : ""}`
                      : ""
                  }`}
                >
                  {p}
                  {label ? <span className="text-muted-foreground ml-1">{label}</span> : null}
                  {count !== undefined ? (
                    <span className="text-muted-foreground ml-1 tabular-nums">
                      · {count.toLocaleString()}
                    </span>
                  ) : null}
                </span>
              );
            })
          )}
        </div>
        <AxiomSummary axioms={axioms} />
      </div>
    </Panel>
  );
}
