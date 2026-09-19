/**
 * 05 本体建模器（EAI-CUSTOM）——真实数据源：/registry-content 三端点.
 *
 * 左栏类层次（subClassOf 树）+ 中栏类详情（附录 A 八项）/公理 + 右栏 YAML 草稿。
 * 编辑流 = 改 YAML 草稿 → 校验建模面（dry-run lint）→ 保存并热重载（原子写+指纹重载）。
 * MVP 编辑面 = YAML 文本；表单化公理编辑后续迭代。
 */
import { useQuery } from "@tanstack/react-query";
import { DraftingCompass } from "lucide-react";
import { useMemo, useState } from "react";

import {
  fetchRegistryContent,
  saveRegistryContent,
  validateRegistryDraft,
  type RegistrySummary,
} from "@/api/registry-api";
import { Chip, PageHeader, Panel } from "@/pages/shared";
import { OntologyCanvas } from "@/components/OntologyCanvas";

interface ClassEntry {
  name: string;
  label: string;
  definition: string;
  parents: string[];
  hasKey: string[];
  etypes: string[];
}

interface ClassRow {
  domain: string;
  cls: ClassEntry;
}

function buildFlat(classes: ClassEntry[]): Array<{ entry: ClassEntry; depth: number }> {
  const byName = new Map(classes.map((c) => [c.name, c]));
  const children = new Map<string, string[]>();
  const roots: string[] = [];
  for (const c of classes) {
    const realParents = c.parents.filter((p) => byName.has(p));
    if (realParents.length === 0) {
      roots.push(c.name);
    } else {
      for (const p of realParents) {
        const list = children.get(p) ?? [];
        list.push(c.name);
        children.set(p, list);
      }
    }
  }
  const out: Array<{ entry: ClassEntry; depth: number }> = [];
  const seen = new Set<string>();
  const walk = (name: string, depth: number) => {
    if (seen.has(name)) return;
    seen.add(name);
    const entry = byName.get(name);
    if (!entry) return;
    out.push({ entry, depth });
    for (const child of children.get(name) ?? []) walk(child, depth + 1);
  };
  for (const name of roots) walk(name, 0);
  for (const c of classes) if (!seen.has(c.name)) out.push({ entry: c, depth: 0 });
  return out;
}

export function ModelerPage() {
  const [selectedFile, setSelectedFile] = useState("doc_graph.yaml");
  const [draft, setDraft] = useState<string | null>(null);
  const [selectedClass, setSelectedClass] = useState<string | null>(null);
  const [summaryOverride, setSummaryOverride] = useState<RegistrySummary | null>(null);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<"edit" | "graph">("edit");

  const filesQuery = useQuery({
    queryKey: ["registry-files"],
    queryFn: async () => {
      const r = await fetch("/api/ontostudio/api/extensions/ontology/registry-content/files", { credentials: "include" });
      if (!r.ok) return { files: [] as string[] };
      return (await r.json()) as { files: string[] };
    },
    staleTime: 60_000,
  });
  const contentQuery = useQuery({
    queryKey: ["registry-content", selectedFile],
    queryFn: () => fetchRegistryContent(selectedFile),
    staleTime: 30_000,
  });
  const content = contentQuery.data;
  const summary = summaryOverride ?? content?.summary ?? null;
  const text = draft ?? content?.raw ?? "";
  const isDirty = draft !== null && draft !== (content?.raw ?? "");

  const allClasses = useMemo(() => {
    if (!summary) return [];
    const out: ClassRow[] = [];
    for (const [domain, dom] of Object.entries(summary.domains)) {
      for (const c of dom.classes) out.push({ domain, cls: c });
    }
    return out;
  }, [summary]);
  const selected = allClasses.find((c) => c.cls.name === selectedClass)?.cls ?? null;

  const axioms = useMemo(() => {
    if (!summary) return [];
    return Object.entries(summary.axioms).flatMap(([domain, a]) => [
      ...a.property_chains.map((c) => ({ domain, tag: "propertyChain", text: `${c.derived} = ${c.chain.join(" → ")}` })),
      ...a.transitive.map((t) => ({ domain, tag: "transitive", text: t })),
      ...a.inverse.map((p) => ({ domain, tag: "inverse", text: p.pair.join(" ⇄ ") })),
      ...a.disjoint.map((d) => ({ domain, tag: "disjoint", text: d })),
    ]);
  }, [summary]);

  const handleValidate = async () => {
    setSaveMsg(null);
    const result = await validateRegistryDraft(selectedFile, text);
    if (result.summary) setSummaryOverride(result.summary);
    setSaveMsg(result.ok ? "✓ 校验通过" : `✗ 校验失败:\n${result.errors.join("\n")}`);
  };

  // 关系图数据（从 summary.classes 的 parents 派生 subClassOf 边）
  const graphClasses = useMemo(() => {
    if (!summary) return [];
    return Object.values(summary.domains).flatMap((dom) =>
      dom.classes.map((c) => ({ name: c.name, label: c.label, definition: c.definition, parents: c.parents })),
    );
  }, [summary]);
  const graphEdges = useMemo(() => {
    const edges: Array<{ source: string; target: string }> = [];
    for (const [, dom] of Object.entries(summary?.domains ?? {})) {
      for (const c of dom.classes) {
        for (const parent of c.parents) {
          edges.push({ source: parent, target: c.name });
        }
      }
    }
    return edges;
  }, [summary]);
  const handleSave = async () => {
    setSaveMsg(null);
    const result = await saveRegistryContent(selectedFile, text);
    contentQuery.refetch();
    setSummaryOverride(null);
    setDraft(null);
    setSaveMsg(`✓ 已保存 · v${result.registry_version} · ${result.fingerprint}`);
  };

  return (
    <div className="p-6">
      <PageHeader
        icon={DraftingCompass}
        title="本体建模器"
        description="元数据描述项对齐 GB/T 48000.3 附录 A · 公理以 OWL 2 RL 表达 · 保存后 SHA 热重载"
        actions={
          <>
            <button
              className="border-border bg-card hover:bg-accent h-9 rounded-md border px-4 text-sm font-medium shadow-xs"
              onClick={handleValidate}
            >
              校验建模面
            </button>
            <button
              className="bg-primary hover:bg-primary/90 text-primary-foreground h-9 rounded-md px-4 text-sm font-medium"
              onClick={handleSave}
              disabled={!isDirty}
            >
              {isDirty ? "保存草稿" : "保存并热重载"}
            </button>
          </>
        }
      />
      {saveMsg ? (
        <div
          className={`${
            saveMsg.startsWith("✓") ? "bg-success/10 text-success" : "bg-destructive/10 text-destructive"
          } mb-3.5 rounded-lg border px-4 py-2.5 text-xs font-medium whitespace-pre-wrap`}
        >
          {saveMsg}
        </div>
      ) : null}
      {/* 视图切换 */}
      <div className="mb-3.5 flex gap-1 bg-muted rounded-lg p-1 w-fit">
        {(["edit", "graph"] as const).map((mode) => (
          <button
            key={mode}
            type="button"
            className={`rounded-md px-4 py-1.5 text-xs font-medium transition-colors ${
              viewMode === mode
                ? "bg-card text-foreground shadow-sm font-semibold"
                : "text-muted-foreground hover:text-foreground"
            }`}
            onClick={() => setViewMode(mode)}
          >
            {mode === "edit" ? "编辑视图" : "关系图"}
          </button>
        ))}
      </div>
      {viewMode === "edit" ? (
      <div className="grid grid-cols-1 gap-3.5 xl:grid-cols-[220px_1fr_340px]">
        {/* 左：类层次 */}
        <Panel title="类层次" subtitle="subClassOf">
          <ul className="p-2 text-[13px]">
            {allClasses.map(({ domain, cls }) => (
              <li key={domain + cls.name}>
                <button
                  type="button"
                  className={`${
                    selectedClass === cls.name
                      ? "bg-sidebar-accent text-primary font-semibold"
                      : "text-muted-foreground hover:bg-accent hover:text-foreground"
                  } flex w-full items-center gap-2 rounded-md px-2.5 py-1 text-left`}
                  onClick={() => setSelectedClass(cls.name)}
                >
                  <span className="text-primary/50 font-mono text-[9px]">{domain.slice(0, 4)}</span>
                  {cls.name}
                </button>
              </li>
            ))}
          </ul>
        </Panel>

        {/* 中：类详情 + 公理 */}
        <div className="flex flex-col gap-3.5">
          <Panel title={selected?.name ?? "选择类"} actions={<Chip tone="primary">owl:Class</Chip>}>
            {selected ? (
              <div className="space-y-2 p-4 text-xs">
                <div className="flex gap-4">
                  <span className="text-muted-foreground w-16 flex-none">IRI</span>
                  <span className="break-all font-mono">
                    {(Object.values(summary?.domains ?? {}).find((d) => d.classes.some((x) => x.name === selected?.name))?.namespace ?? "") + selected.name}
                  </span>
                </div>
                <div className="flex gap-4">
                  <span className="text-muted-foreground w-16 flex-none">标签</span>
                  <span>{selected.label}</span>
                </div>
                <div className="flex gap-4">
                  <span className="text-muted-foreground w-16 flex-none">定义</span>
                  <span>{selected.definition || "—"}</span>
                </div>
                <div className="flex gap-4">
                  <span className="text-muted-foreground w-16 flex-none">父类</span>
                  <span className="font-mono">{selected.parents.join(", ") || "—"}</span>
                </div>
                <div className="flex gap-4">
                  <span className="text-muted-foreground w-16 flex-none">hasKey</span>
                  <span className="font-mono">{selected.hasKey.join(", ") || "—"}</span>
                </div>
                <div className="flex gap-4">
                  <span className="text-muted-foreground w-16 flex-none">etype</span>
                  <span className="font-mono">{selected.etypes.join(", ")}</span>
                </div>
              </div>
            ) : (
              <div className="text-muted-foreground p-4 text-xs">← 从类层次中选择</div>
            )}
          </Panel>
          <Panel title="公理" subtitle="OWL 2 RL" actions={<button className="text-primary text-xs font-medium">新增公理</button>}>
            <div className="flex flex-col gap-2 p-4">
              {axioms.map((axiom) => (
                <div
                  key={axiom.domain + axiom.tag + axiom.text}
                  className="border-border bg-muted flex flex-wrap items-center gap-2.5 rounded-lg border px-3 py-2 text-xs"
                >
                  <span className="bg-primary/10 text-primary rounded px-1.5 py-px font-mono text-[10.5px] font-semibold">
                    {axiom.tag}
                  </span>
                  <code className="font-mono">{axiom.text}</code>
                </div>
              ))}
            </div>
          </Panel>
        </div>

        {/* 右：YAML 草稿 */}
        <Panel title="YAML 草稿" subtitle="formal 段">
          <textarea
            className="bg-code text-code-fg h-[480px] w-full resize-y p-3 font-mono text-[11.5px] leading-relaxed outline-none"
            value={text}
            onChange={(e) => setDraft(e.target.value)}
            spellCheck={false}
          />
        </Panel>
      </div>
      ) : (
      <OntologyCanvas
        classes={graphClasses}
        edgesData={graphEdges}
        selectedName={selectedClass}
        onSelect={setSelectedClass}
      />
      )}
    </div>
  );
}

