/**
 * 05 本体建模器（EAI-CUSTOM, 2026-09-27 原型还原 + 批次 2 画布交互转正）。
 *
 * 骨架 = 三栏（域文件列表 | 编辑器单面板 | 右栏 300px），三模式：
 * - 可视化模式：TBox 画布（真实类层次 + 实例计数 + 属性链）——节点**可拖拽移位**
 *   （视图态，registry 无布局数据不落 YAML，随域切换重置）；「＋子类」进入连线模式
 *   （点选父类完成 subClassOf 加边，写 parents 草稿）；表单父类 chips 可增删（=边编辑）；
 *   新建类实装（草稿追加 + 画布居中出现）。
 * - 表单模式：参照原型的中栏类定义表单 + 对象属性/关系谓词只读视图；字段编辑同样落
 *   draftText（与右栏、画布共用一条草稿管线）。
 * - YAML 源码模式：行号编辑器（结构编辑兜底，schema 校验兜底）。
 * 编辑管线：表单/画布/YAML 均落 draftText（单一草稿）→ 校验 → 保存（fingerprint 乐观
 * 并发 + registry_version 递增 + SHA 热重载）。
 */
import { useQuery, useQueryClient, useQueries } from "@tanstack/react-query";
import {
  Box,
  Check,
  DraftingCompass,
  FileCode2,
  GitBranch,
  Loader2,
  Maximize2,
  Minimize2,
  Plus,
  Save,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";
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

interface ClassEntry {
  name: string;
  label: string;
  definition: string;
  parents: string[];
  hasKey: string[];
  etypes: string[];
}

type ModelerMode = "vis" | "form" | "yaml";

interface FormObjectProperty {
  name: string;
  apiName: string;
  type: string;
  description: string;
  enumValues?: string[];
  filterable?: boolean;
  searchable?: boolean;
}

interface FormObjectType {
  apiName: string;
  displayName: string;
  properties: FormObjectProperty[];
  etypeClassMap: Record<string, string>;
  etypeEnum: string[];
}

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

/** 在 snake_case 下划线后提供换行点（<wbr> 不写入可复制的文本）。 */
function BreakableId({ value }: { value: string }) {
  const parts = value.split("_");
  return (
    <>
      {parts.map((part, index) => (
        <span key={`${part}-${index}`}>
          {index > 0 ? "_" : ""}
          {part}
          {index < parts.length - 1 ? <wbr /> : null}
        </span>
      ))}
    </>
  );
}

/** etype（snake_case）→ 类名（PascalCase），用于无 etype_classes 的 core_graph。 */
function etypeToClassName(etype: string) {
  return etype
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join("");
}

/** 从当前草稿 YAML 提取 object_types 的属性与 etype→class 映射（表单模式只读视图）。 */
function parseObjectTypes(raw: string): FormObjectType[] {
  try {
    const doc = yamlLoad(raw);
    if (!doc || typeof doc !== "object" || Array.isArray(doc)) return [];
    const objectTypes = (doc as Record<string, unknown>).object_types;
    if (!Array.isArray(objectTypes)) return [];
    return objectTypes.map((item) => {
      const ot = asRecord(item);
      const props = Array.isArray(ot.properties) ? ot.properties : [];
      const etypeClasses = asRecord(ot.etype_classes);
      const etypeClassMap: Record<string, string> = {};
      for (const [etype, mapping] of Object.entries(etypeClasses)) {
        const cls = String(asRecord(mapping).class ?? "");
        if (cls) etypeClassMap[etype] = cls;
      }
      const etypeProp = props
        .map((p) => asRecord(p))
        .find((p) => p.name === "etype");
      const etypeEnum = Array.isArray(etypeProp?.enum)
        ? etypeProp.enum.map(String)
        : [];
      return {
        apiName: String(ot.api_name ?? ""),
        displayName: String(ot.display_name ?? ""),
        properties: props.map((p) => {
          const pr = asRecord(p);
          return {
            name: String(pr.name ?? ""),
            apiName: String(pr.api_name ?? pr.name ?? ""),
            type: String(pr.type ?? ""),
            description: String(pr.description ?? ""),
            enumValues: Array.isArray(pr.enum) ? pr.enum.map(String) : undefined,
            filterable: Boolean(pr.filterable),
            searchable: Boolean(pr.searchable),
          };
        }),
        etypeClassMap,
        etypeEnum,
      };
    });
  } catch {
    return [];
  }
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
  const [selectedFile, setSelectedFile] = useState(initialFile ?? "core_graph.yaml");
  const [selectedClass, setSelectedClass] = useState<string | null>(null);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [mode, setMode] = useState<ModelerMode>("vis");
  // 编辑面板最大化（2026-10-02 用户要求）：fixed 覆盖视口，画布随之加高
  const [maximized, setMaximized] = useState(false);
  const [busy, setBusy] = useState<"validate" | "save" | null>(null);
  const isDark = useIsDark();

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
  // 正確處理 eia.yaml 的 etype_classes 嵌套結構和 core_graph.yaml 的 classes 結構
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
  const classTree = useMemo(() => buildTree(allClasses), [allClasses]);

  const formObjectTypes = useMemo(
    () => (mode === "form" ? parseObjectTypes(text) : []),
    [mode, text],
  );
  const selectedObjectType = useMemo(() => {
    if (!selected) return null;
    const byClass = formObjectTypes.find((ot) =>
      Object.values(ot.etypeClassMap).includes(selected.name),
    );
    if (byClass) return byClass;
    return (
      formObjectTypes.find((ot) =>
        ot.etypeEnum.some(
          (etype) =>
            selected.etypes.includes(etype) ||
            etypeToClassName(etype) === selected.name,
        ),
      ) ?? null
    );
  }, [formObjectTypes, selected]);

  const changeMode = useCallback(
    (next: ModelerMode) => {
      setMode(next);
      if (next === "form") {
        setMaximized(false);
        if (!selectedClass && allClasses.length > 0) {
          setSelectedClass(allClasses[0]?.name ?? null);
        }
      }
    },
    [allClasses, selectedClass],
  );

  // 表单模式始终落在一个可选类上（切域 / 删除当前类后自动选首个类）。
  useEffect(() => {
    if (mode === "form" && !selected && allClasses.length > 0) {
      setSelectedClass(allClasses[0]?.name ?? null);
    }
  }, [mode, selected, allClasses]);

  // 窄屏下左栏在前，切到表单后把表单滚入视口，避免“点了没反应”的错觉。
  useEffect(() => {
    if (mode !== "form") return;
    if (!window.matchMedia("(max-width: 900px)").matches) return;
    const timer = window.setTimeout(() => {
      document
        .querySelector(".os-modeler-form-card")
        ?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 80);
    return () => window.clearTimeout(timer);
  }, [mode]);

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
      // EAI-CUSTOM (2026-10-06): 类元数据的 schema 合法载体是 object_types[] 内嵌
      // etype_classes（schemas.py ObjectType extra=forbid）——旧实现写顶层 classes:，
      // 保存恒 422「Extra inputs are not permitted」且对象形态 detail 被 authFetch
      // 吞成裸 "Request failed"，用户看不到真实原因（core_graph.yaml label 编辑实测）。
      const pascal = (et: string) => et.replace(/(^|_)([a-z])/g, (_, _s, c) => c.toUpperCase());
      const root = yamlLoad(text) as Draft;
      const ots = (root.object_types ?? []) as Draft[];
      let ownerApiName: string | null = null;
      let etypeKey: string | null = null;
      for (const ot of ots) {
        const props = (ot.properties ?? []) as Draft[];
        const etypeEnum = (props.find((p) => p.name === "etype")?.enum ?? []) as string[];
        if (etypeEnum.length === 0) continue;
        const ec = (ot.etype_classes ?? {}) as Record<string, Draft>;
        const byMapping = Object.entries(ec).find(([, m]) => m.class === clsName)?.[0];
        const byEtype = etypeEnum.find((et) => pascal(et) === clsName);
        if (byMapping || byEtype) {
          ownerApiName = ot.api_name as string;
          etypeKey = byMapping ?? byEtype ?? null;
          break;
        }
      }
      if (!ownerApiName || !etypeKey) {
        // 类元数据住在其他域文件（如 doc_graph 域部分类声明于 eia.yaml）——写本文件必 422
        setSaveMsg(`✗ 类 ${clsName} 的元数据不在当前文件（声明于其他域 yaml）——请切换到对应文件编辑`);
        return;
      }
      const ok = mutateDraft((obj) => {
        const list = (obj.object_types ?? []) as Draft[];
        const ot = list.find((o) => o.api_name === ownerApiName);
        if (!ot) return;
        const ec = { ...((ot.etype_classes ?? {}) as Record<string, Draft>) };
        ec[etypeKey] = { ...(ec[etypeKey] ?? {}), [field]: value };
        ot.etype_classes = ec;
      });
      if (ok) {
        setSelectedClass(clsName);
      }
    },
    [text, mutateDraft],
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

  const addEtypeToSelected = useCallback(
    (et: string) => {
      if (!selected) return;
      mutateDraft((obj) => {
        const classes = (obj.classes ?? {}) as Draft;
        const entry = (classes[selected.name] ?? {}) as Draft;
        const etypes = new Set([...((entry.etypes as string[]) ?? []), et]);
        classes[selected.name] = { ...entry, etypes: [...etypes] };
        obj.classes = classes;
      });
    },
    [mutateDraft, selected],
  );

  const removeEtypeFromSelected = useCallback(
    (et: string) => {
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
    },
    [mutateDraft, selected],
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
    setBusy("save");
    try {
      const r = await saveRegistryContent(selectedFile, text);
      setSaveMsg(`✓ 已保存 v${r.registry_version}（SHA 热重载生效）`);
      setDraftText(null);
      await qc.invalidateQueries({ queryKey: ["registry-content", selectedFile] });
    } catch (e) {
      setSaveMsg(`✗ 保存失败: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(null);
    }
  }, [selectedFile, text, qc]);

  const handleValidate = useCallback(async () => {
    setBusy("validate");
    try {
      const r = await validateRegistryDraft(selectedFile, text);
      setSaveMsg(r.ok ? "✓ 校验通过（schema/引用/环）" : `✗ 校验失败: ${r.errors.join("; ")}`);
    } catch (e) {
      setSaveMsg(`✗ 校验请求失败: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(null);
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

  const validationState = saveMsg?.startsWith("✓ 校验通过")
    ? "ok"
    : saveMsg?.startsWith("✗ 校验")
      ? "err"
      : "idle";

  const classFormProps = {
    selected,
    namespace: domainSummary?.namespace,
    domainClasses: allClasses.map((c) => c.name),
    onEdit: (field: "label" | "definition", value: string) => {
      if (selected) editClassField(selected.name, field, value);
    },
    onAddParent: (parent: string) => {
      if (selected) addParentEdge(selected.name, parent);
    },
    onRemoveParent: (parent: string) => {
      if (selected) removeParentEdge(selected.name, parent);
    },
    onAddEtype: addEtypeToSelected,
    onRemoveEtype: removeEtypeFromSelected,
  };

  return (
    <div className="os-page-scroll h-full overflow-x-hidden overflow-y-auto">
      <div className="os-page os-modeler-page">
        <PageHeader
          clause="05 · 建模层"
          icon={DraftingCompass}
          title="本体建模器"
          description={`编辑域模型：类 / 属性 / 关系 / 公理，保存前必须通过校验 · ${selectedFile} · registry v${content?.registry_version ?? "—"}`}
          actions={
            <>
              <div
                className="os-seg os-modeler-mode"
                role="group"
                aria-label="编辑模式"
              >
                <button
                  type="button"
                  aria-pressed={mode === "vis"}
                  className={mode === "vis" ? "on" : undefined}
                  onClick={() => changeMode("vis")}
                >
                  可视化建模
                </button>
                <button
                  type="button"
                  aria-pressed={mode === "form"}
                  className={mode === "form" ? "on" : undefined}
                  onClick={() => changeMode("form")}
                >
                  表单模式
                </button>
                <button
                  type="button"
                  aria-pressed={mode === "yaml"}
                  className={mode === "yaml" ? "on" : undefined}
                  onClick={() => changeMode("yaml")}
                >
                  YAML 源码
                </button>
              </div>
              <button
                type="button"
                onClick={handleValidate}
                disabled={busy !== null || !text}
                className="os-btn os-btn-secondary"
                aria-busy={busy === "validate"}
              >
                {busy === "validate" ? (
                  <Loader2 className="animate-spin" />
                ) : (
                  <ShieldCheck />
                )}
                校验
              </button>
              <button
                type="button"
                onClick={handleSave}
                disabled={busy !== null || !text}
                className="os-btn os-btn-primary"
                aria-busy={busy === "save"}
              >
                {busy === "save" ? <Loader2 className="animate-spin" /> : <Save />}
                保存
              </button>
            </>
          }
        />
        {saveMsg ? <SaveBanner msg={saveMsg} /> : null}
        {contentQuery.isLoading ? (
          <div className="os-modeler-skeleton-grid" aria-label="加载 registry">
            <div className="os-card os-modeler-skeleton-side">
              <div className="os-skeleton h-9 w-full" />
              <div className="os-skeleton h-9 w-full" />
              <div className="os-skeleton h-9 w-full" />
            </div>
            <div className="os-card os-modeler-skeleton-main">
              <div className="os-skeleton h-10 w-2/3" />
              <div className="os-skeleton h-[360px] w-full" />
            </div>
            <div className="os-card os-modeler-skeleton-rail">
              <div className="os-skeleton h-28 w-full" />
              <div className="os-skeleton h-28 w-full" />
            </div>
          </div>
        ) : (
          <div className="os-modeler-grid">
            {/* 左栏：域文件 + 类树 */}
            <aside className="os-modeler-side">
              <Panel
                title="域文件"
                actions={
                  !filesQuery.isLoading && files.length > 0 ? (
                    <span className="os-pill os-pill-gray">{files.length}</span>
                  ) : undefined
                }
                className="os-modeler-files"
              >
                <div className="os-modeler-file-list">
                  {filesQuery.isLoading ? (
                    <div className="os-modeler-loading-row">
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      加载域文件…
                    </div>
                  ) : (
                    files.map((file) => (
                      <FileTab
                        key={file}
                        name={file}
                        active={selectedFile === file}
                        dirty={selectedFile === file && dirty}
                        classCount={contentCountFor(file)}
                        onClick={() => setSelectedFile(file)}
                      />
                    ))
                  )}
                </div>
                <div className="os-modeler-footnote">
                  以上均为 <b>TBox</b>（术语层声明）；实例（ABox）落{" "}
                  <code>dg_*</code> 表与内核图，不经 yaml。
                </div>
                <div className="os-modeler-tree-hd">
                  <span>类树</span>
                  <span>{allClasses.length} 类</span>
                </div>
                <div className="os-modeler-tree">
                  {allClasses.length === 0 ? (
                    <div className="os-modeler-empty-sm">当前域暂无类声明</div>
                  ) : (
                    classTree.map(({ cls, depth }) => {
                      const count = instancesOf(cls);
                      return (
                        <button
                          key={cls.name}
                          type="button"
                          onClick={() => setSelectedClass(cls.name)}
                          className={cn(
                            "os-modeler-tree-row",
                            selectedClass === cls.name && "is-on",
                          )}
                          style={{ paddingLeft: `${9 + depth * 13}px` }}
                          title={`${cls.name}${cls.label ? ` · ${cls.label}` : ""}`}
                        >
                          <Box className="os-modeler-tree-icon" />
                          <span className="os-modeler-tree-main">
                            <span className="os-modeler-tree-name">{cls.name}</span>
                            <span className="os-modeler-tree-label">
                              {cls.label || "—"}
                            </span>
                          </span>
                          <span className="os-modeler-tree-count">
                            {count ?? "—"}
                          </span>
                        </button>
                      );
                    })
                  )}
                </div>
              </Panel>
            </aside>

            {/* 中：编辑器 / 表单 + 谓词与公理 */}
            <div className="os-modeler-center">
              {mode === "form" ? (
                <FormModePanel
                  {...classFormProps}
                  objectType={selectedObjectType}
                  predicates={domainPredicates}
                  counts={countByPredicate}
                  labels={predicateLabelsQuery.data}
                  file={selectedFile}
                  version={content?.registry_version}
                  validationState={validationState}
                  onEditYaml={() => changeMode("yaml")}
                />
              ) : (
                <div
                  className={cn(
                    "os-card os-modeler-editor",
                    maximized && "is-max",
                  )}
                >
                <div className="os-modeler-editor-hd">
                  <FileCode2 className="os-modeler-file-icon" />
                  <b className="os-modeler-editor-title">{selectedFile}</b>
                  <span className="os-modeler-editor-meta">
                    v{content?.registry_version ?? "—"} ·{" "}
                    {content?.fingerprint?.slice(0, 6) ?? "—"}
                  </span>
                  {dirty ? (
                    <span className="os-pill os-pill-warn">未保存</span>
                  ) : (
                    <span className="os-pill os-pill-gray">已同步</span>
                  )}
                  <div className="os-modeler-editor-actions">
                    <button
                      type="button"
                      onClick={() => setMaximized((m) => !m)}
                      title={maximized ? "还原面板" : "最大化编辑面板"}
                      aria-label={maximized ? "还原面板" : "最大化编辑面板"}
                      className="os-modeler-icon-btn"
                    >
                      {maximized ? <Minimize2 /> : <Maximize2 />}
                    </button>
                  </div>
                </div>

                {mode === "vis" ? (
                  <div className="os-modeler-vis">
                    <div className="os-modeler-toolbar">
                      <button
                        type="button"
                        onClick={addClass}
                        className="os-btn os-btn-primary os-btn-sm"
                      >
                        <Plus />
                        新建类
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
                          "os-btn os-btn-secondary os-btn-sm",
                          connectChild && "is-on",
                        )}
                      >
                        <GitBranch />
                        子类连线
                      </button>
                      <button
                        type="button"
                        disabled={!selectedClass}
                        onClick={() => removeClass(selectedClass as string)}
                        title="删除前先查引用（属性链/实例），确认后从草稿移除"
                        className="os-btn os-btn-ghost is-danger os-btn-sm"
                      >
                        <Trash2 />
                        删除
                      </button>
                      {connectChild ? (
                        <span className="os-modeler-connect-hint">
                          <GitBranch />
                          连线模式：为 {connectChild} 点击父类节点（Esc 取消）
                        </span>
                      ) : (
                        <span className="os-modeler-toolbar-hint">
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
                      onRebase={(map) => setPositionOverrides(map)}
                      draftEdges={draftEdges}
                      heightClass={maximized ? "min-h-0 flex-1" : "h-[440px]"}
                    />
                  </div>
                ) : (
                  <div className="os-modeler-yaml">
                    <YamlEditor
                      text={text}
                      isDark={isDark}
                      height={maximized ? "calc(100vh - 105px)" : "560px"}
                      onChange={(v) => {
                        setDraftText(v);
                        setSaveMsg(null);
                      }}
                    />
                  </div>
                )}
                </div>
              )}

              {!maximized || mode === "form" ? (
                <PredicateAxiomPanel
                  predicates={domainPredicates}
                  counts={countByPredicate}
                  labels={predicateLabelsQuery.data}
                  axioms={axioms}
                />
              ) : null}
            </div>

            {/* 右栏：类定义 / 校验 / 公理 */}
            <aside className="os-modeler-rail">
              {mode !== "form" ? <ClassDetailForm {...classFormProps} /> : null}

              <Panel
                title="校验面板"
                subtitle="保存前必须通过"
                actions={
                  <span
                    className={cn(
                      "os-pill",
                      validationState === "ok" && "os-pill-ok",
                      validationState === "err" && "os-pill-err",
                      validationState === "idle" && "os-pill-gray",
                    )}
                  >
                    {validationState === "ok"
                      ? "已通过"
                      : validationState === "err"
                        ? "未通过"
                        : "待校验"}
                  </span>
                }
                className="os-modeler-validation"
              >
                <div className="os-modeler-check-list">
                  {[
                    ["Schema 结构", "schema 字段与类型合法"],
                    ["引用完整", "父类、谓词、公理目标可解析"],
                    ["继承无环", "subClassOf 链无循环"],
                    ["命名规范", "类标识符合 namespace 约定"],
                  ].map(([title, desc]) => (
                    <div
                      key={title}
                      className={cn(
                        "os-modeler-check",
                        validationState === "ok" && "is-ok",
                        validationState === "err" && "is-err",
                      )}
                    >
                      <span className="os-modeler-check-ic">
                        {validationState === "err" ? <X /> : <Check />}
                      </span>
                      <div>
                        <b>{title}</b>
                        <span>{desc}</span>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="os-modeler-validation-foot">
                  <button
                    type="button"
                    onClick={handleValidate}
                    disabled={busy !== null || !text}
                    className="os-btn os-btn-secondary"
                    aria-busy={busy === "validate"}
                  >
                    {busy === "validate" ? (
                      <Loader2 className="animate-spin" />
                    ) : (
                      <ShieldCheck />
                    )}
                    校验当前草稿
                  </button>
                  <p>
                    {validationState === "ok"
                      ? "上次校验通过，可继续保存。"
                      : validationState === "err"
                        ? "上次校验未通过，详见顶部横幅。"
                        : "检查 schema / 引用 / 环，结果同步显示在顶部横幅。"}
                  </p>
                </div>
              </Panel>

              <AxiomsPanel axioms={axioms} predicates={domainPredicates} />
            </aside>
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
    <div className={cn("os-modeler-banner", ok ? "is-ok" : "is-err")}>
      {ok ? <Check /> : <X />}
      <span>{msg.replace(/^[✓✗]\s*/, "")}</span>
    </div>
  );
}

// 域文件角色徽标（2026-10-06）：两份 yaml 均为 TBox（术语层声明），分工不同——
// doc_graph=域无关结构骨架（实体/关系/证据容器+审核动作），eia=环评业务域词汇
// （etype/谓词/公理/类标签）。实例（ABox）落 dg_* 表与内核图，不经 yaml。
const FILE_ROLES: Record<string, { tag: string; desc: string }> = {
  "core_graph.yaml": { tag: "TBox · 结构骨架", desc: "域无关底座：实体/关系/证据容器 + 审核动作" },
  "eia.yaml": { tag: "TBox · 业务域词汇", desc: "环评域 etype/谓词/公理/类标签声明" },
  "market.yaml": { tag: "TBox · 营销域词汇", desc: "营销域 etype/谓词/公理/类标签声明（天玛智控定制 v1）" },
};

function FileTab({
  name,
  active,
  dirty,
  classCount,
  onClick,
}: {
  name: string;
  active: boolean;
  dirty?: boolean;
  classCount?: number;
  onClick: () => void;
}) {
  const role = FILE_ROLES[name];
  return (
    <button
      type="button"
      onClick={onClick}
      title={role?.desc}
      className={cn("os-modeler-file", active && "is-on")}
    >
      <FileCode2 className="os-modeler-file-icon" />
      <span className="os-modeler-file-main">
        <span className="os-modeler-file-name">{name}</span>
        <span className="os-modeler-file-meta">
          <span className="os-modeler-file-tag">{role?.tag ?? "TBox"}</span>
          <span
            className={cn(
              "os-modeler-file-status",
              active && dirty && "is-dirty",
            )}
          >
            {active && dirty ? "编辑中" : "已保存"}
          </span>
        </span>
      </span>
      <span className="os-modeler-file-count">
        {classCount !== undefined ? `${classCount} 类` : "—"}
      </span>
    </button>
  );
}

interface ClassFormProps {
  selected: ClassEntry | null;
  namespace?: string;
  domainClasses: string[];
  onEdit: (field: "label" | "definition", value: string) => void;
  onAddParent: (parent: string) => void;
  onRemoveParent: (parent: string) => void;
  onAddEtype: (et: string) => void;
  onRemoveEtype: (et: string) => void;
}

function ClassFields({
  selected,
  namespace,
  domainClasses,
  onEdit,
  onAddParent,
  onRemoveParent,
  onAddEtype,
  onRemoveEtype,
  className,
}: ClassFormProps & { className?: string }) {
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

  if (!selected) return null;
  return (
    <div className={cn("os-modeler-form", className)}>
        <label className="os-modeler-field">
          <span>类标识 IRI 局部</span>
          <input
            defaultValue={selected.name}
            key={`name-${selected.name}`}
            readOnly
            className="os-modeler-input os-modeler-readonly"
          />
        </label>
        <label className="os-modeler-field">
          <span>显示名 label</span>
          <input
            defaultValue={selected.label}
            key={`label-${selected.name}`}
            onBlur={(e) => {
              if (e.target.value !== selected.label)
                onEdit("label", e.target.value);
            }}
            className="os-modeler-input"
          />
        </label>
        <div className="os-modeler-field">
          <span>父类 parents</span>
          <div className="os-modeler-combo" ref={parentBoxRef}>
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
              className="os-modeler-input"
            />
            {parentOpen ? (
              <div className="os-modeler-combo-list">
                {parentCandidates.length === 0 ? (
                  <div className="os-modeler-empty-sm">
                    无可添加的父类（已全部选中）
                  </div>
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
                      className="os-modeler-combo-item"
                    >
                      {c}
                    </button>
                  ))
                )}
              </div>
            ) : null}
          </div>
          <div className="os-modeler-chips">
            {localParents.length === 0 ? (
              <span className="os-modeler-hint">—（根类）</span>
            ) : (
              localParents.map((p) => (
                <span key={p} className="os-modeler-chip">
                  {p}
                  <button
                    type="button"
                    aria-label={`移除父类 ${p}`}
                    onClick={() => removeParentLocal(p)}
                  >
                    <X />
                  </button>
                </span>
              ))
            )}
          </div>
        </div>

        <label className="os-modeler-field">
          <span>命名空间 namespace</span>
          <input
            value={namespace ?? "—"}
            readOnly
            title={namespace ?? ""}
            className="os-modeler-input os-modeler-readonly"
          />
        </label>

        <label className="os-modeler-field is-wide">
          <span>定义 definition</span>
          <textarea
            defaultValue={selected.definition}
            key={`def-${selected.name}`}
            onBlur={(e) => {
              if (e.target.value !== selected.definition)
                onEdit("definition", e.target.value);
            }}
            rows={3}
            className="os-modeler-textarea"
          />
        </label>

        <label className="os-modeler-field is-wide">
          <span>键 hasKey</span>
          <input
            defaultValue={selected.hasKey.join(", ")}
            key={`key-${selected.name}`}
            readOnly
            placeholder="如 name"
            className="os-modeler-input os-modeler-readonly"
          />
        </label>

        <div className="os-modeler-field is-wide">
          <span>实例类型 etypes</span>
          <div className="os-modeler-chips">
            {localEtypes.length === 0 ? (
              <span className="os-modeler-hint">—</span>
            ) : (
              localEtypes.map((et) => (
                <span key={et} className="os-modeler-chip">
                  {et}
                  <button
                    type="button"
                    aria-label={`移除实例类型 ${et}`}
                    onClick={() => removeEtypeLocal(et)}
                  >
                    <X />
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
              placeholder="＋ 输入后回车"
              aria-label="添加实例类型"
              className="os-modeler-inline-input"
            />
          </div>
          <span className="os-modeler-hint">
            由 registry etype_class_map 派生；Enter 添加，✕ 移除（写草稿
            etypes 数组）
          </span>
        </div>
    </div>
  );
}

function FormModePanel({
  selected,
  objectType,
  predicates,
  counts,
  labels,
  file,
  version,
  validationState,
  onEditYaml,
  ...classProps
}: ClassFormProps & {
  objectType: FormObjectType | null;
  predicates: string[];
  counts: Map<string, number>;
  labels?: Map<string, string>;
  file: string;
  version?: number;
  validationState: "ok" | "err" | "idle";
  onEditYaml: () => void;
}) {
  const statusLabel =
    validationState === "ok"
      ? "已通过"
      : validationState === "err"
        ? "未通过"
        : "待校验";
  return (
    <div className="os-card os-modeler-form-card">
      <div className="os-modeler-form-hd">
        <div className="os-modeler-form-hd-icon">
          <Box />
        </div>
        <div className="os-modeler-form-hd-main">
          <div className="os-modeler-form-kicker">类定义 · {file}</div>
          <b>{selected?.name ?? "表单模式"}</b>
          <span>{selected?.label || "从左侧类树选择一个类开始编辑"}</span>
        </div>
        <div className="os-modeler-form-hd-right">
          <span
            className={cn(
              "os-pill",
              validationState === "ok" && "os-pill-ok",
              validationState === "err" && "os-pill-err",
              validationState === "idle" && "os-pill-gray",
            )}
          >
            {statusLabel}
          </span>
          <span className="os-pill os-pill-gray">v{version ?? "—"}</span>
        </div>
      </div>

      {selected ? (
        <>
          <ClassFields
            {...classProps}
            selected={selected}
            className="os-modeler-form-center"
          />
          <section className="os-modeler-form-section">
            <div className="os-modeler-form-section-hd">
              <b>属性与关系</b>
              <span>
                {objectType
                  ? `${objectType.displayName || objectType.apiName} · ${objectType.properties.length} 个对象属性`
                  : "域级词表（只读）"}
              </span>
              <button
                type="button"
                onClick={onEditYaml}
                className="os-btn os-btn-ghost os-btn-sm"
              >
                在 YAML 中编辑
              </button>
            </div>

            <div className="os-modeler-form-subhd">对象属性</div>
            {objectType && objectType.properties.length > 0 ? (
              <div className="os-modeler-form-table-wrap">
                <table className="os-modeler-form-table is-props">
                  <thead>
                    <tr>
                      <th>属性名</th>
                      <th>标识</th>
                      <th>类型</th>
                      <th>约束</th>
                    </tr>
                  </thead>
                  <tbody>
                    {objectType.properties.map((p) => {
                      const constraints = [
                        p.filterable ? "可筛选" : "",
                        p.searchable ? "可搜索" : "",
                      ].filter(Boolean);
                      return (
                        <tr key={`${p.name}-${p.apiName}`}>
                          <td className="is-main">{p.description || p.name}</td>
                          <td className="is-mono">
                            <BreakableId value={p.apiName} />
                          </td>
                          <td>
                            <code>{p.type || "—"}</code>
                            {p.enumValues && p.enumValues.length > 0 ? (
                              <span className="os-modeler-form-enum">
                                {p.enumValues.length} 枚举
                              </span>
                            ) : null}
                          </td>
                          <td className="is-muted">
                            {constraints.length > 0
                              ? constraints.join(" · ")
                              : "—"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="os-modeler-form-empty">
                当前类未匹配到对象类型属性；可在 YAML 模式查看 object_types。
              </div>
            )}

            <div className="os-modeler-form-subhd">关系谓词（域词表）</div>
            {predicates.length > 0 ? (
              <div className="os-modeler-form-table-wrap">
                <table className="os-modeler-form-table is-relations">
                  <thead>
                    <tr>
                      <th>谓词</th>
                      <th>中文</th>
                      <th className="is-num">三元组</th>
                    </tr>
                  </thead>
                  <tbody>
                    {predicates.map((p) => (
                      <tr key={p}>
                        <td className="is-mono">
                          <BreakableId value={p} />
                        </td>
                        <td>{labels?.get(p) ?? "—"}</td>
                        <td className="is-num">
                          {counts.get(p)?.toLocaleString() ?? "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="os-modeler-form-empty">
                本域暂无关系谓词声明。
              </div>
            )}

            <p className="os-modeler-form-note">
              表单字段与可视化 / YAML 共用同一份草稿；对象属性来自当前类所属对象类型，
              关系谓词为域词表，当前只读。
            </p>
          </section>
        </>
      ) : (
        <div className="os-modeler-empty">
          <Box />
          <b>尚未选择类</b>
          <span>从左侧类树选择一个类开始表单编辑。</span>
        </div>
      )}
    </div>
  );
}

function ClassDetailForm({ selected, ...props }: ClassFormProps) {
  if (!selected) {
    return (
      <Panel
        title="选中元素 · 类"
        subtitle="类定义"
        icon={Box}
        className="os-modeler-class-panel"
      >
        <div className="os-modeler-empty">
          <Box />
          <b>尚未选择类</b>
          <span>从左侧类树或画布中选择一个类开始编辑。</span>
        </div>
      </Panel>
    );
  }
  return (
    <Panel
      title={selected.name}
      subtitle="类定义"
      icon={Box}
      actions={<Chip tone="primary">owl:Class</Chip>}
      className="os-modeler-class-panel"
    >
      <ClassFields selected={selected} {...props} />
    </Panel>
  );
}

function AxiomsPanel({
  axioms,
  predicates,
}: {
  axioms?: RegistryAxioms;
  predicates: string[];
}) {
  const groups: Array<{ title: string; items: string[] }> = [
    {
      title: "传递 transitive",
      items: axioms?.transitive ?? [],
    },
    {
      title: "不相交 disjoint",
      items: axioms?.disjoint ?? [],
    },
    {
      title: "逆 inverse",
      items: (axioms?.inverse ?? []).map((inv) => inv.pair.join(" ↔ ")),
    },
  ];
  return (
    <Panel
      title="公理"
      subtitle="自动派生 · 结构只读"
      className="os-modeler-axioms-panel"
    >
      <div className="os-modeler-axioms">
        <div className="os-modeler-axiom-group">
          <h4>属性链 property_chains</h4>
          <div className="os-modeler-axiom-list">
            {(axioms?.property_chains ?? []).length === 0 ? (
              <span className="os-modeler-hint">—</span>
            ) : (
              (axioms?.property_chains ?? []).map((chain) => (
                <span key={chain.derived} className="os-modeler-chain">
                  {chain.chain.join(" ∘ ")}
                  <b>⇒ {chain.derived}</b>
                </span>
              ))
            )}
          </div>
        </div>
        {groups.map((group) => (
          <div key={group.title} className="os-modeler-axiom-group">
            <h4>{group.title}</h4>
            <div className="os-modeler-axiom-list">
              {group.items.length === 0 ? (
                <span className="os-modeler-hint">—</span>
              ) : (
                group.items.map((item) => (
                  <span key={item} className="os-modeler-axiom-chip">
                    {item}
                  </span>
                ))
              )}
            </div>
          </div>
        ))}
        <p className="os-modeler-hint">
          {predicates.length > 0
            ? `本域声明 ${predicates.length} 个谓词；编辑 axioms 请切换 YAML 源码。`
            : "本域暂无谓词声明。"}
        </p>
      </div>
    </Panel>
  );
}

/** YAML 行号编辑器（CodeMirror 6：语法高亮 + 行号 + 自动缩进 + 括号匹配）。 */
function YamlEditor({
  text,
  isDark,
  height,
  onChange,
}: {
  text: string;
  isDark: boolean;
  height: string;
  onChange: (v: string) => void;
}) {
  return (
    <CodeMirror
      value={text}
      height={height}
      theme={isDark ? "dark" : "light"}
      extensions={[yaml()]}
      onChange={onChange}
      basicSetup={{
        lineNumbers: true,
        foldGutter: true,
        highlightActiveLine: true,
        autocompletion: false,
      }}
      style={{ fontSize: "12.5px", fontFamily: "var(--mono, monospace)" }}
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
  onRebase,
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
  /** stage 生长：传入按像素冻结好的新几何整表（父组件只落 state）。 */
  onRebase: (map: Map<string, Pos>) => void;
  draftEdges: Array<{ key: string; parent: string; child: string }>;
  /** 最大化模式下传更高的高度类。 */
  heightClass?: string;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [zoom, setZoom] = useState(1);
  // 画布视口高度 = 容器实测；stage 布局高度 ≥ 视口——拖近底缘时自动生长（无限画布语义），
  // 生长时其余节点按 px 冻结（换算成新几何写 overrides），只有被拖节点下移。
  // 几何以 ref 为准：同步多次 pointermove 期间 React state 不 flush，闭包旧值会让
  // 生长算术逐帧复利（实测节点被甩到 top 1997%）。
  const [viewportH, setViewportH] = useState(STAGE_H);
  const [stageH, setStageH] = useState(STAGE_H);
  const stageHRef = useRef(STAGE_H);
  const posRef = useRef<Map<string, Pos>>(positions);
  posRef.current = positions;
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      setViewportH(el.clientHeight);
      stageHRef.current = Math.max(stageHRef.current, el.clientHeight);
      setStageH(stageHRef.current);
    });
    ro.observe(el);
    setViewportH(el.clientHeight);
    stageHRef.current = Math.max(stageHRef.current, el.clientHeight);
    setStageH(stageHRef.current);
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
    const orig = posRef.current.get(name) ?? { x: 50, y: 50 };
    dragRef.current = { name, startX: e.clientX, startY: e.clientY, orig, moved: false };
    e.currentTarget.setPointerCapture(e.pointerId);
  };

  const onNodePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    const rect = containerRef.current?.getBoundingClientRect();
    if (!drag || !rect) return;
    const h = stageHRef.current;
    // 缩放下：屏幕位移换算回 stage 百分比——水平除以 stage 视觉宽（=容器宽×zoom），
    // 竖直除以 stage 视觉高（=h×zoom）。
    const dxPct = ((e.clientX - drag.startX) / (rect.width * zoom)) * 100;
    const dyPct = ((e.clientY - drag.startY) / (h * zoom)) * 100;
    if (!drag.moved && Math.hypot(dxPct, dyPct) < 1) return; // 死区：区分点击
    drag.moved = true;
    const x = Math.min(96, Math.max(4, drag.orig.x + dxPct));
    const rawY = Math.max(6, drag.orig.y + dyPct);
    // 视口跟随：把被拖节点滚进视口。scrollIntoView(nearest) 交给浏览器钳制——
    // 手算 scrollTop 会被提交前旧 scrollHeight/滚动锚定轮番拽回（实测恒停 338）。
    // rAF 等提交后执行。
    const followView = (name: string) => {
      const el = containerRef.current;
      if (!el) return;
      requestAnimationFrame(() => {
        el.querySelector(`[data-testid="tbox-node-${CSS.escape(name)}"]`)
          ?.scrollIntoView({ block: "nearest", behavior: "auto" });
      });
    };
    // 底部自动生长：被拖节点底缘逼近 stage 底（28px 余量）→ stage 加高，其余节点
    // 按像素位置冻结进新几何（写 overrides），仅被拖节点继续随指针下移。
    const rawPx = (rawY / 100) * h;
    if (rawPx > h - 28) {
      const nextH = Math.min(Math.ceil(rawPx) + 48, viewportH * 3);
      const k = h / nextH;
      const next = new Map<string, Pos>();
      posRef.current.forEach((p, n) => next.set(n, { x: p.x, y: p.y * k }));
      // 被拖节点：px → 新几何百分比（rawPx/nextH×100）；写成 px×k 会把节点甩出画布
      const draggedY = (rawPx / nextH) * 100;
      next.set(drag.name, { x, y: draggedY });
      posRef.current = next;
      stageHRef.current = nextH;
      onRebase(next);
      setStageH(nextH);
      followView(drag.name);
      // 坐标基点一并重置到当前指针——orig 已含本段位移，再累加全量 dy 会双重计账
      //（实测 stage 冲到 3× 上限、节点 top 1997%）。
      dragRef.current = {
        ...drag,
        startX: e.clientX,
        startY: e.clientY,
        orig: { x, y: draggedY },
      };
      return;
    }
    const y = Math.min(94, rawY);
    onNodeMove(drag.name, { x, y });
    followView(drag.name);
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
    <div className={cn("os-modeler-canvas-wrap", heightClass)}>
      <div
        ref={containerRef}
        className="os-modeler-canvas"
        style={{
          // overflow-anchor none：Chrome 滚动锚定会在生长重排时拽回 scrollTop，破坏视口跟随
          overflowAnchor: "none",
        }}
        data-testid="tbox-canvas"
      >
        {/* sizer 撑出滚动范围；stage 原尺寸经 scale(zoom) 放大，节点/边随缩放 */}
        <div
          className="os-modeler-canvas-sizer"
          style={{ width: `${zoom * 100}%`, height: `${stageH * zoom}px` }}
        >
          <div
            className="os-modeler-canvas-stage"
            style={{
              width: `${100 / zoom}%`,
              height: stageH,
              transform: `scale(${zoom})`,
            }}
          >
            <svg
              className="os-modeler-edges"
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
                    stroke={
                      isPending || edge.draftOnly
                        ? "var(--warn-700)"
                        : "var(--main-300)"
                    }
                    strokeOpacity={isPending ? 0.9 : edge.draftOnly ? 0.75 : 0.8}
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
                    if (e.key === "Enter" || e.key === " ")
                      onNodeClick(cls.name);
                  }}
                  className={cn(
                    "os-modeler-node-wrap",
                    connectChild && isPending && "is-pending",
                  )}
                  style={{
                    left: `${pos2.x}%`,
                    top: `${pos2.y}%`,
                    cursor: connectChild ? "crosshair" : "grab",
                  }}
                  title={`${cls.name}${cls.label ? ` · ${cls.label}` : ""}`}
                  data-testid={`tbox-node-${cls.name}`}
                >
                  <span
                    className={cn(
                      "os-modeler-node",
                      isSel && "is-sel",
                      isPending && "is-pending",
                    )}
                  >
                    <span className="os-modeler-node-name">{cls.name}</span>
                    <span className="os-modeler-node-label">
                      {cls.label || cls.name}
                    </span>
                  </span>
                  {count !== null ? (
                    <span className="os-modeler-node-count">
                      {count.toLocaleString()} 实例
                    </span>
                  ) : null}
                </div>
              );
            })}
            {connectChild ? (
              <div className="os-modeler-connect-banner">
                连线模式：点击目标父类节点（Esc 取消）
              </div>
            ) : null}
          </div>
        </div>
      </div>
      {/* 缩放工具栏（相对画布容器固定，不随 sizer 滚动） */}
      <div className="os-modeler-zoom">
        <button
          type="button"
          onClick={() =>
            setZoom((z) => Math.max(0.5, Number((z - 0.25).toFixed(2))))
          }
          title="缩小"
          aria-label="缩小画布"
        >
          −
        </button>
        <span>{Math.round(zoom * 100)}%</span>
        <button
          type="button"
          onClick={() =>
            setZoom((z) => Math.min(2.5, Number((z + 0.25).toFixed(2))))
          }
          title="放大"
          aria-label="放大画布"
        >
          +
        </button>
        <button
          type="button"
          onClick={() => setZoom(1)}
          title="重置缩放"
          className="is-text"
        >
          重置
        </button>
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
    <span className="os-modeler-hint">
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
    <Panel
      title="谓词与公理"
      subtitle="本域关系词汇使用情况与自动派生规则"
      className="os-modeler-predicates"
    >
      <div className="os-modeler-predicate-body">
        <div className="os-modeler-predicate-head">
          <span>谓词（关系类型）</span>
          <span>{predicates.length} 个</span>
        </div>
        <div className="os-modeler-predicate-list">
          {predicates.length === 0 ? (
            <span className="os-modeler-hint">—</span>
          ) : (
            predicates.map((p) => {
              const label = labels?.get(p);
              const count = counts.get(p);
              return (
                <span
                  key={p}
                  className="os-modeler-predicate-chip"
                  title={`本域定义的关系类型${label ? `：${label}` : ""}${
                    count !== undefined
                      ? `；图中该谓词 ${count.toLocaleString()} 条三元组${count === 0 ? "（已定义未使用）" : ""}`
                      : ""
                  }`}
                >
                  <b>{p}</b>
                  {label ? <span>{label}</span> : null}
                  {count !== undefined ? (
                    <em>{count.toLocaleString()}</em>
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

/** CodeMirror needs an explicit theme; follow the app's class-based dark mode. */
function useIsDark() {
  const [dark, setDark] = useState(
    () =>
      typeof document !== "undefined" &&
      document.documentElement.classList.contains("dark"),
  );
  useEffect(() => {
    const root = document.documentElement;
    const sync = () => setDark(root.classList.contains("dark"));
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(root, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);
  return dark;
}
