/**
 * 05 本体建模器（EAI-CUSTOM，2026-09-27 原型重构）——双模式。
 *
 * 表单模式（默认）：类层次树 + 可编辑字段（label/definition）+ 公理面板（结构只读，
 * 结构编辑走 YAML 模式）——编辑落草稿 → 校验 → 保存（fingerprint 乐观并发 + 版本递增）。
 * YAML 源码模式（专家）：整篇可编辑，校验/保存同一管线。画布式拖拽建模属批次 2（TODOS）。
 * 保存前必须过 /registry-content/validate——两种模式同一校验管线。
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { DraftingCompass, Loader2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { load as yamlLoad, dump as yamlDump } from "js-yaml";

import {
  fetchRegistryContent,
  saveRegistryContent,
  validateRegistryDraft,
  type RegistryAxioms,
  type RegistrySummary,
} from "@/api/registry-api";
import { Chip, PageHeader, Panel } from "@/pages/shared";
import { cn } from "@/lib/utils";

interface ClassEntry {
  name: string;
  label: string;
  definition: string;
  parents: string[];
  hasKey: string[];
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

export function ModelerPage() {
  const qc = useQueryClient();
  const [selectedFile, setSelectedFile] = useState("doc_graph.yaml");
  const [selectedClass, setSelectedClass] = useState<string | null>(null);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [mode, setMode] = useState<"form" | "yaml">("form");
  const [busy, setBusy] = useState(false);

  const contentQuery = useQuery({
    queryKey: ["registry-content", selectedFile],
    queryFn: () => fetchRegistryContent(selectedFile),
    staleTime: 30_000,
  });
  const content = contentQuery.data;
  const summary = content?.summary ?? null;

  // 草稿文本：null = 与远端一致；表单/YAML 任一编辑后落这里（单一真相，两种模式共享校验/保存）
  const [draftText, setDraftText] = useState<string | null>(null);
  useEffect(() => {
    setDraftText(null); // 切文件 / 远端刷新 → 草稿复位
    setSelectedClass(null);
  }, [content?.raw, selectedFile]);

  const remoteText = content?.raw ?? "";
  const text = draftText ?? remoteText;
  const dirty = draftText !== null && draftText !== remoteText;

  const draftObj = useMemo(() => {
    if (!text) return null;
    try {
      return yamlLoad(text) as Draft;
    } catch {
      return null;
    }
  }, [text]);

  const allClasses = useMemo(() => {
    if (!summary) return [];
    const out: ClassEntry[] = [];
    for (const dom of Object.values(summary.domains)) {
      for (const c of dom.classes) {
        out.push({
          name: c.name,
          label: c.label,
          definition: c.definition,
          parents: c.parents,
          hasKey: c.hasKey,
        });
      }
    }
    return out;
  }, [summary]);

  const tree = useMemo(() => buildTree(allClasses), [allClasses]);
  const selected = allClasses.find((c) => c.name === selectedClass) ?? null;
  const domainName = useMemo(() => selectedFile.replace(/\.yaml$/, ""), [selectedFile]);
  const axioms: RegistryAxioms | undefined = summary?.axioms?.[domainName];
  const domainPredicates = summary?.domains?.[domainName]?.predicates ?? [];

  /** 表单编辑：改 draftObj 里 classes.<name>.<field>，重序列化为草稿文本。 */
  const editClassField = useCallback(
    (clsName: string, field: "label" | "definition", value: string) => {
      try {
        const obj = yamlLoad(text) as Draft;
        const classes = (obj.classes ?? {}) as Draft;
        const entry = (classes[clsName] ?? {}) as Draft;
        classes[clsName] = { ...entry, [field]: value };
        obj.classes = classes;
        setDraftText(yamlDump(obj, { lineWidth: -1 }));
        setSaveMsg(null);
      } catch {
        setSaveMsg("✗ 当前文本不是合法 YAML，表单编辑不可用——请先在 YAML 模式修正");
      }
    },
    [text],
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

  return (
    <div className="p-6">
      <PageHeader
        icon={DraftingCompass}
        title="本体建模器"
        description="双模式：表单编辑（类字段 + 公理查看）与 YAML 源码共享同一草稿与校验/保存管线 · 元数据对齐 GB/T 48000.3 附录 A · 保存后 SHA 热重载"
        actions={
          <>
            <div className="border-border flex overflow-hidden rounded-lg border">
              <button
                type="button"
                onClick={() => setMode("form")}
                className={cn(
                  "px-3 py-1.5 text-xs font-medium",
                  mode === "form"
                    ? "bg-primary/10 text-primary font-semibold"
                    : "bg-card text-muted-foreground hover:bg-accent",
                )}
              >
                表单模式
              </button>
              <button
                type="button"
                onClick={() => setMode("yaml")}
                className={cn(
                  "px-3 py-1.5 text-xs font-medium",
                  mode === "yaml"
                    ? "bg-primary/10 text-primary font-semibold"
                    : "bg-card text-muted-foreground hover:bg-accent",
                )}
              >
                YAML 源码
              </button>
            </div>
            <button
              className="border-border bg-card hover:bg-accent h-9 rounded-md border px-4 text-sm font-medium shadow-xs disabled:opacity-50"
              onClick={handleValidate}
              disabled={busy || !text}
            >
              校验
            </button>
            <button
              className="bg-primary hover:bg-primary/90 text-primary-foreground h-9 rounded-md px-4 text-sm font-medium disabled:opacity-50"
              onClick={handleSave}
              disabled={busy || !text}
            >
              {busy ? <Loader2 className="mr-1 inline h-3.5 w-3.5 animate-spin" /> : null}
              保存并热重载
            </button>
          </>
        }
      />
      {saveMsg ? <SaveBanner msg={saveMsg} /> : null}
      {dirty ? (
        <div className="bg-warning/15 text-warning mb-3.5 rounded-lg border px-4 py-2.5 text-xs font-medium">
          有未保存修改——保存前必须通过校验
        </div>
      ) : null}
      {contentQuery.isLoading ? (
        <div className="text-muted-foreground py-16 text-center text-xs">
          <Loader2 className="mx-auto mb-2 h-4 w-4 animate-spin" />
          加载 registry…
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3.5 xl:grid-cols-[220px_1fr_340px]">
          <ClassTreePanel
            classes={allClasses}
            selected={selectedClass}
            onSelect={setSelectedClass}
          />
          {mode === "form" ? (
            <div className="flex flex-col gap-3.5">
              <ClassDetailForm
                selected={selected}
                onEdit={(field, value) =>
                  selected && editClassField(selected.name, field, value)
                }
              />
              <AxiomsPanel axioms={axioms} predicates={domainPredicates} />
            </div>
          ) : (
            <Panel title="YAML 源码" subtitle={`${selectedFile} · 整篇可编辑`}>
              <textarea
                className="bg-code text-code-fg h-[560px] w-full resize-y p-3 font-mono text-[11.5px] leading-relaxed outline-none"
                value={text}
                onChange={(e) => {
                  setDraftText(e.target.value);
                  setSaveMsg(null);
                }}
                spellCheck={false}
              />
            </Panel>
          )}
          <RightRail
            mode={mode}
            draftObj={draftObj}
            text={text}
            file={selectedFile}
            version={content?.registry_version}
            fingerprint={content?.fingerprint}
          />
        </div>
      )}
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

function ClassTreePanel({
  classes,
  selected,
  onSelect,
}: {
  classes: ClassEntry[];
  selected: string | null;
  onSelect: (name: string) => void;
}) {
  const tree = useMemo(() => buildTree(classes), [classes]);
  return (
    <Panel title="类层次" subtitle="subClassOf">
      <ul className="p-2 text-[13px]">
        {tree.map(({ cls, depth }) => (
          <li key={cls.name} style={{ paddingLeft: depth * 16 }}>
            <button
              type="button"
              className={`${selected === cls.name ? "bg-sidebar-accent text-primary font-semibold" : "text-muted-foreground hover:bg-accent hover:text-foreground"} flex w-full items-center rounded-md px-2.5 py-1 text-left`}
              onClick={() => onSelect(cls.name)}
            >
              {cls.name}
            </button>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function ClassDetailForm({
  selected,
  onEdit,
}: {
  selected: ClassEntry | null;
  onEdit: (field: "label" | "definition", value: string) => void;
}) {
  if (!selected) {
    return (
      <Panel title="选择类" actions={<Chip tone="primary">owl:Class</Chip>}>
        <div className="text-muted-foreground p-4 text-xs">← 从类层次中选择一个类开始编辑</div>
      </Panel>
    );
  }
  return (
    <Panel
      title={selected.name}
      subtitle="可编辑字段：label / definition（父类与键属结构编辑，走 YAML 模式）"
      actions={<Chip tone="primary">owl:Class</Chip>}
    >
      <div className="space-y-3 p-4">
        <label className="block">
          <span className="text-muted-foreground text-[11px] font-medium">显示名 label</span>
          <input
            defaultValue={selected.label}
            key={`label-${selected.name}`}
            onBlur={(e) => {
              if (e.target.value !== selected.label) onEdit("label", e.target.value);
            }}
            className="border-input focus:border-primary mt-1 h-8 w-full rounded-md border px-2.5 font-mono text-xs outline-none"
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
        <div className="grid grid-cols-2 gap-3">
          <ReadonlyChips title="父类 parents" items={selected.parents} hint="结构编辑走 YAML 模式" />
          <ReadonlyChips title="键 hasKey" items={selected.hasKey} hint="结构编辑走 YAML 模式" />
        </div>
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
      <span className="text-muted-foreground/70 mt-0.5 block text-[10px]">{hint}</span>
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
    <Panel title="公理与谓词" subtitle="结构只读 · 编辑走 YAML 模式">
      <div className="space-y-3 p-4 text-xs">
        <div>
          <span className="text-muted-foreground text-[11px] font-medium">谓词 predicates</span>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {predicates.length === 0 ? (
              <span className="text-muted-foreground text-[11px]">—</span>
            ) : (
              predicates.map((p) => (
                <span
                  key={p}
                  className="border-border rounded-full border px-2 py-0.5 font-mono text-[10.5px]"
                >
                  {p}
                </span>
              ))
            )}
          </div>
        </div>
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
        <div className="grid grid-cols-3 gap-3">
          <ReadonlyChips title="传递 transitive" items={axioms?.transitive ?? []} hint="" />
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
          <ReadonlyChips
            title="不相交 disjoint"
            items={(axioms?.disjoint ?? []).map((d) => `[${d}]`)}
            hint=""
          />
        </div>
      </div>
    </Panel>
  );
}

function RightRail({
  mode,
  draftObj,
  text,
  file,
  version,
  fingerprint,
}: {
  mode: "form" | "yaml";
  draftObj: Draft | null;
  text: string;
  file: string;
  version?: number;
  fingerprint?: string;
}) {
  return (
    <div className="flex flex-col gap-3.5">
      <Panel title="当前版本">
        <div className="space-y-1.5 p-4 text-xs">
          <div className="flex justify-between">
            <span className="text-muted-foreground">文件</span>
            <span className="font-mono">{file}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">registry_version</span>
            <span className="font-mono">v{version ?? "—"}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">fingerprint</span>
            <span className="font-mono">{fingerprint?.slice(0, 12) ?? "—"}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">YAML 合法</span>
            <span className={draftObj ? "text-success" : "text-destructive"}>
              {text ? (draftObj ? "✓" : "✗ 解析失败") : "—"}
            </span>
          </div>
        </div>
      </Panel>
      {mode === "form" ? (
        <Panel title="YAML 预览" subtitle="当前草稿">
          <textarea
            className="bg-code text-code-fg h-[420px] w-full resize-y p-3 font-mono text-[11.5px] leading-relaxed outline-none"
            value={text}
            readOnly
            spellCheck={false}
          />
        </Panel>
      ) : (
        <Panel title="使用提示">
          <div className="text-muted-foreground space-y-1.5 p-4 text-[11.5px] leading-relaxed">
            <p>· 保存前必须通过校验（schema/引用/环）</p>
            <p>· 保存按 fingerprint 乐观并发——他人已保存时会返回冲突</p>
            <p>· 保存成功即 SHA 热重载，下一次 infer 用新词表</p>
            <p>· 结构编辑（父类/键/公理）直接改本模式文本</p>
          </div>
        </Panel>
      )}
    </div>
  );
}
