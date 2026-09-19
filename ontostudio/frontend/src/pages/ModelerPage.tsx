/**
 * 05 本体建模器（EAI-CUSTOM）——真实数据 + 结构化 CRUD.
 *
 * 草稿模型 = js-yaml 解析的 registry 对象；表单编辑 → 草稿 → 序列化保存。
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { DraftingCompass } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { load as yamlLoad, dump as yamlDump } from "js-yaml";

import {
  fetchRegistryContent,
  saveRegistryContent,
  validateRegistryDraft,
  type RegistrySummary,
} from "@/api/registry-api";
import { Chip, PageHeader, Panel } from "@/pages/shared";

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
    else for (const p of rp) { const l = children.get(p) ?? []; l.push(c.name); children.set(p, l); }
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
  for (const c of classes) if (!seen.has(c.name)) out.push({ cls: c, depth: 0 });
  return out;
}

type Draft = Record<string, unknown>;

export function ModelerPage() {
  const qc = useQueryClient();
  const [selectedFile, setSelectedFile] = useState("doc_graph.yaml");
  const [selectedClass, setSelectedClass] = useState<string | null>(null);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  const contentQuery = useQuery({
    queryKey: ["registry-content", selectedFile],
    queryFn: () => fetchRegistryContent(selectedFile),
    staleTime: 30_000,
  });
  const content = contentQuery.data;
  const summary = content?.summary ?? null;

  const draftObj = useMemo(() => {
    if (!content?.raw) return null;
    try { return yamlLoad(content.raw) as Draft; } catch { return null; }
  }, [content?.raw]);

  const allClasses = useMemo(() => {
    if (!summary) return [];
    const out: ClassEntry[] = [];
    for (const dom of Object.values(summary.domains)) {
      for (const c of dom.classes) {
        out.push({ name: c.name, label: c.label, definition: c.definition, parents: c.parents, hasKey: c.hasKey });
      }
    }
    return out;
  }, [summary]);

  const tree = useMemo(() => buildTree(allClasses), [allClasses]);
  const selected = allClasses.find((c) => c.name === selectedClass) ?? null;

  const handleSave = useCallback(async () => {
    if (!draftObj) return;
    const yamlText = yamlDump(draftObj);
    try {
      const r = await saveRegistryContent(selectedFile, yamlText);
      setSaveMsg(`✓ 已保存 v${r.registry_version}`);
      qc.invalidateQueries({ queryKey: ["registry-content", selectedFile] });
    } catch (e) {
      setSaveMsg(`✗ 保存失败: ${e instanceof Error ? e.message : String(e)}`);
    }
  }, [selectedFile, draftObj, qc]);

  const handleValidate = useCallback(async () => {
    if (!draftObj) return;
    const yamlText = yamlDump(draftObj);
    try {
      const r = await validateRegistryDraft(selectedFile, yamlText);
      setSaveMsg(r.ok ? "✓ 校验通过" : `✗ 校验失败: ${r.errors.join("; ")}`);
    } catch (e) {
      setSaveMsg(`✗ 校验请求失败: ${e instanceof Error ? e.message : String(e)}`);
    }
  }, [selectedFile, draftObj]);

  return (
    <div className="p-6">
      <PageHeader
        icon={DraftingCompass}
        title="本体建模器"
        description="元数据描述项对齐 GB/T 48000.3 附录 A · 公理以 OWL 2 RL 表达 · 保存后 SHA 热重载"
        actions={
          <>
            <button className="border-border bg-card hover:bg-accent h-9 rounded-md border px-4 text-sm font-medium shadow-xs" onClick={handleValidate}>
              校验建模面
            </button>
            <button className="bg-primary hover:bg-primary/90 text-primary-foreground h-9 rounded-md px-4 text-sm font-medium" onClick={handleSave}>
              保存并热重载
            </button>
          </>
        }
      />
      {saveMsg ? <SaveBanner msg={saveMsg} /> : null}
      <div className="grid grid-cols-1 gap-3.5 xl:grid-cols-[220px_1fr_340px]">
        <ClassTreePanel classes={allClasses} selected={selectedClass} onSelect={setSelectedClass} />
        <ClassDetailAndAxioms selected={selected} />
        <YamlPreview draftObj={draftObj} />
      </div>
    </div>
  );
}

// ── 子组件 ──

function SaveBanner({ msg }: { msg: string }) {
  const ok = msg.startsWith("✓");
  return (
    <div className={`${ok ? "bg-success/10 text-success" : "bg-destructive/10 text-destructive"} mb-3.5 rounded-lg border px-4 py-2.5 text-xs font-medium whitespace-pre-wrap`}>
      {msg}
    </div>
  );
}

function ClassTreePanel({ classes, selected, onSelect }: {
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

function ClassDetailAndAxioms({ selected }: { selected: ClassEntry | null }) {
  return (
    <div className="flex flex-col gap-3.5">
      <Panel title={selected?.name ?? "选择类"} actions={<Chip tone="primary">owl:Class</Chip>}>
        {selected ? (
          <div className="space-y-2 p-4 text-xs">
            {[
              ["IRI", `…#${selected.name}`],
              ["标签", selected.label],
              ["定义", selected.definition || "—"],
              ["父类", selected.parents.join(", ") || "—"],
              ["hasKey", selected.hasKey.join(", ") || "—"],
            ].map(([key, value]) => (
              <div key={key} className="flex gap-4">
                <span className="text-muted-foreground w-16 flex-none">{key}</span>
                <span className="font-mono break-all">{value}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-muted-foreground p-4 text-xs">← 从类层次中选择</div>
        )}
      </Panel>
    </div>
  );
}

function YamlPreview({ draftObj }: { draftObj: Draft | null }) {
  return (
    <Panel title="YAML 预览" subtitle="当前草稿">
      <textarea
        className="bg-code text-code-fg h-[480px] w-full resize-y p-3 font-mono text-[11.5px] leading-relaxed outline-none"
        value={draftObj ? yamlDump(draftObj, { lineWidth: -1 }) : ""}
        readOnly
        spellCheck={false}
      />
    </Panel>
  );
}
