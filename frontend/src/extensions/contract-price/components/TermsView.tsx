"use client";

/**
 * EAI-CUSTOM: cpa v3 货物分类术语（spec 2026-10-14 §2.4）。
 * 视觉=原型屏幕②（.wolf/tmp/cpa-v3-prototype.html）：页头 / 统计小卡 ×3 /
 * 工具栏（新建+搜索+来源过滤 pill）/ 术语表 / chips 编辑抽屉。
 * 交互习语复用 LibraryView：flash 通知条（timer ref + 卸载清理）/ 右侧抽屉骨架。
 */

import {
  ArrowLeftRight,
  Info,
  Loader2,
  Pencil,
  Plus,
  Tags,
  Trash2,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatCard } from "@/extensions/contract-price/components/StatCard";
import { Pill } from "@/extensions/contract-price/components/ui/bits";
import { cn } from "@/lib/utils";

import {
  useNameSplits,
  useNameSplitMutations,
  useTerms,
  useTermsMutations,
} from "../hooks";
import type { CpaNameSplit, CpaTerm } from "../types";

import { PageHeader } from "./PageHeader";

function SourceBadge({ source }: { source: CpaTerm["source"] }) {
  return (
    <Pill tone={source === "manual" ? "info" : "gray"}>
      {source === "manual" ? "手动" : "自动合并"}
    </Pill>
  );
}

export function TermsView() {
  const termsQ = useTerms();
  const muts = useTermsMutations();
  // 易混名称区分表(2026-10-22, 术语表对偶)
  const splitsQ = useNameSplits();
  const splitMuts = useNameSplitMutations();
  const [splitDlg, setSplitDlg] = useState<{
    a: string;
    b: string;
    reason: string;
  } | null>(null);

  const all = useMemo(() => termsQ.data?.items ?? [], [termsQ.data]);
  const [q, setQ] = useState("");
  const [sourceFilter, setSourceFilter] = useState<
    "manual" | "auto_merge" | null
  >(null);

  const [editor, setEditor] = useState<{ term: CpaTerm | null } | null>(null);
  const [canon, setCanon] = useState("");
  const [aliases, setAliases] = useState<string[]>([]);
  const [aliasDraft, setAliasDraft] = useState("");

  // flash: sonner 右下角 toast(对齐知识工厂),不再内嵌通知条——列表不位移。
  const flash = (kind: "ok" | "err", text: string) =>
    kind === "ok" ? toast.success(text) : toast.error(text);

  // Esc 关闭术语编辑抽屉（镜像 LibraryView 的 window keydown 写法）
  useEffect(() => {
    if (!editor) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setEditor(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [editor]);

  const openEditor = (t: CpaTerm | null) => {
    setCanon(t?.canonical ?? "");
    setAliases(t?.aliases ?? []);
    setAliasDraft("");
    setEditor({ term: t });
  };

  const saveTerm = async () => {
    const name = canon.trim();
    if (!name) return;
    try {
      if (editor?.term) {
        await muts.updateTerm.mutateAsync({
          id: editor.term.id,
          patch: { canonical: name, aliases },
        });
      } else {
        await muts.createTerm.mutateAsync({ canonical: name, aliases });
      }
      setEditor(null);
      flash("ok", "术语已保存，下次「聚类分析」生效");
    } catch (e) {
      flash("err", `保存失败：${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const doDelete = async (t: CpaTerm) => {
    try {
      await muts.deleteTerm.mutateAsync(t.id);
      if (editor?.term?.id === t.id) setEditor(null);
      flash("ok", "术语已删除");
    } catch (e) {
      flash("err", `删除失败：${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const filtered = all.filter((t) => {
    if (sourceFilter && t.source !== sourceFilter) return false;
    if (!q) return true;
    const needle = q.toLowerCase();
    return (
      t.canonical.toLowerCase().includes(needle) ||
      t.aliases.some((a) => a.toLowerCase().includes(needle))
    );
  });

  const manualCount = all.filter((t) => t.source === "manual").length;
  const autoCount = all.length - manualCount;
  const enabledCount = all.filter((t) => t.enabled).length;
  const disabledCount = all.length - enabledCount;
  const aliasTotal = all.reduce((s, t) => s + t.alias_count, 0);
  const editorPending = editor?.term
    ? muts.updateTerm.isPending
    : muts.createTerm.isPending;

  return (
    <div className="flex h-full flex-col gap-3 px-4 pt-3 pb-4">
      {/* 页头 */}
      <PageHeader
        title="货物分类术语"
        description="命中同一术语（规范名或任一别名）的分项在聚类时强制归入同簇 · 修改后下次「聚类分析」生效"
        icon={<Tags />}
      />

      {/* 统计小卡 ×3（指标格样式，cpa UI 重构规范 §2-2） */}
      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard label="术语总数" value={all.length} tone="accent" />
        <StatCard label="别名总数" value={aliasTotal} />
        <StatCard
          label="启用中"
          value={enabledCount}
          hint={disabledCount ? `${disabledCount} 条已停用` : "全部启用"}
        />
      </div>

      {/* 工具栏 */}
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={() => openEditor(null)}>
          <Plus className="mr-1 h-3.5 w-3.5" /> 新建术语
        </Button>
        <Input
          placeholder="搜索规范名 / 别名…"
          aria-label="搜索术语"
          className="h-8 w-44"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <span className="flex-1" />
        <Button
          variant={sourceFilter === "manual" ? "secondary" : "outline"}
          size="sm"
          aria-pressed={sourceFilter === "manual"}
          onClick={() =>
            setSourceFilter((s) => (s === "manual" ? null : "manual"))
          }
        >
          手动 {manualCount}
        </Button>
        <Button
          variant={sourceFilter === "auto_merge" ? "secondary" : "outline"}
          size="sm"
          aria-pressed={sourceFilter === "auto_merge"}
          onClick={() =>
            setSourceFilter((s) => (s === "auto_merge" ? null : "auto_merge"))
          }
        >
          自动合并 {autoCount}
        </Button>
      </div>

      {/* 术语表 */}
      <div className="min-h-[300px] flex-1 overflow-auto rounded-lg border">
        {termsQ.isError ? (
          <p className="text-destructive p-4 text-sm">
            术语加载失败：{String(termsQ.error)}
          </p>
        ) : termsQ.isLoading ? (
          <div className="text-muted-foreground flex items-center gap-2 p-4 text-sm">
            <Loader2 className="h-4 w-4 animate-spin" /> 加载中…
          </div>
        ) : filtered.length === 0 ? (
          <div className="text-muted-foreground rounded-lg border border-dashed py-16 text-center text-sm">
            {all.length === 0
              ? "还没有术语。点击「新建术语」登记规范名与别名，聚类分析时命中术语的分项强制同簇。"
              : "没有符合当前筛选条件的术语"}
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-muted/50 text-muted-foreground border-b text-left text-xs">
                <th className="px-2 py-2">规范名</th>
                <th className="px-2 py-2">别名</th>
                <th className="w-24 px-2 py-2">来源</th>
                <th className="w-24 px-2 py-2 text-right">已关联分项</th>
                <th className="w-16 px-2 py-2">启用</th>
                <th className="w-32 px-2 py-2">操作</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((t) => (
                <tr
                  key={t.id}
                  className={cn(
                    "hover:bg-muted/50 border-b last:border-b-0",
                    !t.enabled && "opacity-60",
                  )}
                >
                  <td className="px-2 py-2 font-medium">{t.canonical}</td>
                  <td className="px-2 py-2">
                    <div className="flex flex-wrap gap-1">
                      {t.aliases.slice(0, 3).map((a) => (
                        <span
                          key={a}
                          className="bg-muted text-muted-foreground rounded px-1.5 py-0.5 text-xs"
                        >
                          {a}
                        </span>
                      ))}
                      {t.aliases.length > 3 && (
                        <span className="text-muted-foreground rounded border px-1.5 py-0.5 text-xs">
                          +{t.aliases.length - 3}
                        </span>
                      )}
                      {t.aliases.length === 0 && (
                        <span className="text-muted-foreground text-xs">—</span>
                      )}
                    </div>
                  </td>
                  <td className="px-2 py-2">
                    <SourceBadge source={t.source} />
                  </td>
                  <td className="text-muted-foreground px-2 py-2 text-right tabular-nums">
                    {t.item_count} 项
                  </td>
                  <td className="px-2 py-2">
                    <label className="relative inline-flex h-4 w-7 shrink-0 cursor-pointer items-center">
                      <input
                        type="checkbox"
                        className="peer sr-only"
                        checked={t.enabled}
                        aria-label={`启用 ${t.canonical}`}
                        onChange={(e) => {
                          const enabled = e.target.checked;
                          void muts.updateTerm
                            .mutateAsync({ id: t.id, patch: { enabled } })
                            .catch((err: unknown) =>
                              flash(
                                "err",
                                `更新失败：${err instanceof Error ? err.message : String(err)}`,
                              ),
                            );
                        }}
                      />
                      <span className="bg-muted peer-checked:bg-primary absolute inset-0 rounded-full transition-colors" />
                      <span className="bg-background border-border relative ml-0.5 h-3 w-3 rounded-full border shadow-sm transition-transform peer-checked:translate-x-3" />
                    </label>
                  </td>
                  <td className="px-2 py-2">
                    <div className="flex items-center justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 px-2 text-xs"
                        onClick={() => openEditor(t)}
                      >
                        <Pencil className="mr-1 h-3 w-3" /> 编辑
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive hover:text-destructive h-7 w-7 p-0"
                        aria-label={`删除 ${t.canonical}`}
                        disabled={muts.deleteTerm.isPending}
                        onClick={() => doDelete(t)}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <p className="text-muted-foreground text-xs">
        「自动合并」来自分组审核页的手动合并操作，自动登记为术语；「已关联分项」为当前库内命中该术语（含别名）的分项行数。
      </p>

      {/* 术语编辑抽屉（同 LibraryView 抽屉骨架：role=dialog aria-modal + Escape 关闭） */}
      {editor && (
        <div
          className="fixed inset-0 z-50 flex justify-end bg-black/45"
          role="dialog"
          aria-modal="true"
          aria-label="术语编辑"
          onClick={() => setEditor(null)}
        >
          <aside
            className="bg-card flex h-full w-full max-w-xl flex-col border-l shadow-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-2 border-b px-4 py-3">
              <h3 className="min-w-0 flex-1 truncate text-base font-semibold">
                {editor.term
                  ? `编辑术语 · ${editor.term.canonical}`
                  : "新建术语"}
              </h3>
              <Button variant="ghost" size="sm" onClick={() => setEditor(null)}>
                ✕
              </Button>
            </div>
            <div className="min-h-0 flex-1 space-y-4 overflow-auto p-4">
              <div className="space-y-1.5">
                <label htmlFor="term-canonical" className="text-sm font-medium">
                  规范名
                </label>
                <Input
                  id="term-canonical"
                  autoFocus
                  placeholder="如：锚杆"
                  value={canon}
                  onChange={(e) => setCanon(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && saveTerm()}
                />
                <p className="text-muted-foreground text-xs">
                  聚类时作为该组簇的锚定名称；命中任一别名的分项与其强制同簇。
                </p>
              </div>
              <div className="space-y-1.5">
                <span className="text-sm font-medium">别名（回车添加）</span>
                <div className="flex min-h-16 flex-wrap content-start gap-1.5 rounded-md border p-2">
                  {aliases.length === 0 ? (
                    <span className="text-muted-foreground text-xs">
                      暂无别名
                    </span>
                  ) : (
                    aliases.map((a, i) => (
                      <span
                        key={a}
                        className="bg-muted text-foreground inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs"
                      >
                        {a}
                        <button
                          aria-label={`移除别名 ${a}`}
                          className="text-muted-foreground hover:text-destructive"
                          onClick={() =>
                            setAliases((arr) => arr.filter((_, j) => j !== i))
                          }
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </span>
                    ))
                  )}
                </div>
                <Input
                  placeholder="输入别名后回车，如：树脂锚杆"
                  value={aliasDraft}
                  onChange={(e) => setAliasDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && aliasDraft.trim()) {
                      e.preventDefault();
                      const v = aliasDraft.trim();
                      if (!aliases.includes(v))
                        setAliases((arr) => [...arr, v]);
                      setAliasDraft("");
                    }
                  }}
                />
              </div>
              <div className="bg-muted/30 text-muted-foreground flex items-start gap-2 rounded-md border p-3 text-xs">
                <Info className="text-info mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>
                  生效机制：强制同簇（pin
                  语义）——名称归一化去空白后比对，不改变提取结果，仅影响「聚类分析」分组。
                </span>
              </div>
            </div>
            <div className="flex justify-end gap-2 border-t px-4 py-3">
              <Button variant="outline" onClick={() => setEditor(null)}>
                取消
              </Button>
              <Button
                onClick={saveTerm}
                disabled={!canon.trim() || editorPending}
              >
                {editorPending ? "保存中…" : "保存术语"}
              </Button>
            </div>
          </aside>
        </div>
      )}

      {/* ── 易混名称区分表（术语表对偶: 近名异物→聚类显性分开,2026-10-22）── */}
      <div className="space-y-2">
        <div className="flex items-center gap-3">
          <span className="text-foreground text-base font-semibold">
            易混名称区分表
          </span>
          <span className="text-muted-foreground text-xs">
            近名异物 → 聚类显性分开（区分优先于归并；下次「聚类分析」生效）
          </span>
          <span className="flex-1" />
          <Button
            size="sm"
            variant="outline"
            onClick={() => setSplitDlg({ a: "", b: "", reason: "" })}
          >
            <Plus className="mr-1 h-3.5 w-3.5" /> 新建区分规则
          </Button>
        </div>
        {splitsQ.isLoading ? (
          <div className="text-muted-foreground flex items-center gap-2 py-4 text-sm">
            <Loader2 className="h-4 w-4 animate-spin" /> 加载中…
          </div>
        ) : (splitsQ.data?.items ?? []).length === 0 ? (
          <div className="text-muted-foreground rounded-lg border border-dashed p-4 text-sm">
            暂无区分规则。同类货物因名称近似被错并一簇时（如「管内穿线
            铜芯导线」与 「桥架内穿线
            铜芯导线」），在此登记一对名称即可在下次聚类时强制分开；
            手动把货物移出簇也会自动捕获规则。
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-muted/50 text-muted-foreground border-b text-left text-xs">
                <th className="px-3 py-2">名称 A</th>
                <th className="w-8 px-2 py-2" />
                <th className="px-3 py-2">名称 B</th>
                <th className="px-3 py-2">区分理由</th>
                <th className="w-20 px-3 py-2">来源</th>
                <th className="w-20 px-3 py-2">启用</th>
                <th className="w-16 px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {(splitsQ.data?.items ?? []).map((s) => (
                <SplitRow
                  key={s.id}
                  split={s}
                  onToggle={(enabled) =>
                    splitMuts.updateSplit.mutate(
                      { id: s.id, patch: { enabled } },
                      {
                        onError: (e) =>
                          flash(
                            "err",
                            `切换失败：${e instanceof Error ? e.message : String(e)}`,
                          ),
                      },
                    )
                  }
                  onDelete={() =>
                    splitMuts.deleteSplit.mutate(s.id, {
                      onSuccess: () => flash("ok", "区分规则已删除"),
                      onError: (e) =>
                        flash(
                          "err",
                          `删除失败：${e instanceof Error ? e.message : String(e)}`,
                        ),
                    })
                  }
                />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* 新建区分规则对话框 */}
      {splitDlg && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4"
          role="dialog"
          aria-modal="true"
          aria-label="新建区分规则"
          onClick={() => setSplitDlg(null)}
        >
          <div
            className="bg-card w-full max-w-md space-y-3 rounded-lg border p-5 shadow-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-foreground text-base font-semibold">
              新建区分规则
            </h3>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">名称 A</label>
              <Input
                autoFocus
                value={splitDlg.a}
                placeholder="如：管内穿线 铜芯导线"
                onChange={(e) =>
                  setSplitDlg((d) => (d ? { ...d, a: e.target.value } : d))
                }
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">名称 B</label>
              <Input
                value={splitDlg.b}
                placeholder="如：桥架内穿线 铜芯导线"
                onChange={(e) =>
                  setSplitDlg((d) => (d ? { ...d, b: e.target.value } : d))
                }
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">区分理由（可选）</label>
              <Input
                value={splitDlg.reason}
                placeholder="如：敷设方式不同，单价不同"
                onChange={(e) =>
                  setSplitDlg((d) => (d ? { ...d, reason: e.target.value } : d))
                }
              />
            </div>
            <div className="flex justify-end gap-2 pt-1">
              <Button variant="outline" onClick={() => setSplitDlg(null)}>
                取消
              </Button>
              <Button
                disabled={
                  !splitDlg.a.trim() ||
                  !splitDlg.b.trim() ||
                  splitMuts.createSplit.isPending
                }
                onClick={() =>
                  splitMuts.createSplit.mutate(
                    {
                      name_a: splitDlg.a.trim(),
                      name_b: splitDlg.b.trim(),
                      reason: splitDlg.reason.trim() || undefined,
                    },
                    {
                      onSuccess: () => {
                        setSplitDlg(null);
                        flash("ok", "区分规则已保存，下次「聚类分析」生效");
                      },
                      onError: (e) =>
                        flash(
                          "err",
                          `保存失败：${e instanceof Error ? e.message : String(e)}`,
                        ),
                    },
                  )
                }
              >
                {splitMuts.createSplit.isPending ? "保存中…" : "保存规则"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function SplitRow({
  split,
  onToggle,
  onDelete,
}: {
  split: CpaNameSplit;
  onToggle: (enabled: boolean) => void;
  onDelete: () => void;
}) {
  return (
    <tr className="hover:bg-muted/50 border-b last:border-b-0">
      <td className="px-3 py-2">{split.name_a}</td>
      <td className="text-muted-foreground px-2 py-2">
        <ArrowLeftRight className="h-3.5 w-3.5" />
      </td>
      <td className="px-3 py-2">{split.name_b}</td>
      <td className="text-muted-foreground px-3 py-2 text-xs">
        {split.reason ?? "—"}
      </td>
      <td className="px-3 py-2">
        <Pill tone={split.source === "manual" ? "info" : "gray"}>
          {split.source === "manual" ? "手动" : "自动捕获"}
        </Pill>
      </td>
      <td className="px-3 py-2">
        <input
          type="checkbox"
          aria-label={`启用 ${split.name_a} 与 ${split.name_b} 的区分`}
          className="accent-primary h-3.5 w-3.5 cursor-pointer"
          checked={split.enabled}
          onChange={(e) => onToggle(e.target.checked)}
        />
      </td>
      <td className="px-3 py-2 text-right">
        <Button
          variant="ghost"
          size="sm"
          className="text-destructive hover:text-destructive h-7 w-7 p-0"
          aria-label={`删除 ${split.name_a} 与 ${split.name_b} 的区分规则`}
          onClick={onDelete}
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      </td>
    </tr>
  );
}
