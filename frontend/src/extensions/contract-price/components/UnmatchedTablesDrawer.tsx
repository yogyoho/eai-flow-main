"use client";

/** 未匹配表抽屉: 逐表展示页码/表名/OCR表头 → "生成规则草稿"(打开 SeedEditorDrawer)
 *  → 保存规则 → "重解析本文档"(走 OCR 缓存,秒级)。
 *  已保存规则的表标记"已保存规则"并从重解析门槛中剔除——否则保存动作不会改动
 *  parse_meta 快照,门槛永远锁死,闭环走不通。
 *  savedKeys 由父层持有(配置 PUT 成功后 key 才入集合,单一事实源),抽屉只读;
 *  保存期间经 saving 透传 SeedEditorDrawer 禁用"保存规则",防误标/重复提交。 */

import { FileWarning, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  draftFromHeader,
  SeedEditorDrawer,
  type SeedDraft,
} from "@/extensions/contract-price/components/SeedEditorDrawer";
import type { UnmatchedTable } from "@/extensions/contract-price/types";

interface Props {
  open: boolean;
  fileName: string;
  tables: UnmatchedTable[];
  savedKeys: Set<string>; // 已保存规则的表键(以 文件名:页:表序 为键,父层持有,PUT 成功后加入)
  onClose: () => void;
  onCreateSeed: (seed: SeedDraft, key: string) => void; // 保存规则(上层写入 config,成功后父层标记 savedKeys)
  onReparse: () => void; // 重解析本文档(缓存路径)
  reparsePending?: boolean;
  saving?: boolean; // 规则保存请求进行中(禁用 SeedEditorDrawer 的保存按钮)
}

export function UnmatchedTablesDrawer({
  open,
  fileName,
  tables,
  savedKeys,
  onClose,
  onCreateSeed,
  onReparse,
  reparsePending = false,
  saving = false,
}: Props) {
  const [draft, setDraft] = useState<{
    key: string;
    seed: SeedDraft;
    header: string[];
  } | null>(null);
  if (!open) return null;

  const tableKey = (t: UnmatchedTable) =>
    `${fileName}:${t.page}:${t.table_idx}`;
  const remaining = tables.filter((t) => !savedKeys.has(tableKey(t)));

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-black/40"
      onClick={onClose}
    >
      <div
        className="bg-background h-full w-[560px] max-w-[94vw] overflow-y-auto border-l p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FileWarning className="h-5 w-5 text-amber-600" />
            <div>
              <h2 className="text-lg font-bold">
                未识别的表格（{tables.length}）
              </h2>
              <p className="text-muted-foreground text-xs">
                {fileName} · 与任何定位规则都不匹配,未提取
              </p>
            </div>
          </div>
          <Button size="icon" variant="ghost" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="space-y-3">
          {tables.map((t) => (
            <div
              key={`${t.page}-${t.table_idx}`}
              className="rounded-lg border p-3"
            >
              <div className="flex items-center justify-between">
                <div className="text-sm font-medium">
                  第 {t.page} 页 · 表 {t.table_idx + 1}
                  {t.title ? (
                    <span className="text-muted-foreground ml-2">
                      {t.title}
                    </span>
                  ) : null}
                  <span className="text-muted-foreground ml-2 text-xs">
                    {t.row_count}行×{t.col_count}列
                  </span>
                  {savedKeys.has(tableKey(t)) && (
                    <span className="ml-2 text-xs text-emerald-600">
                      已保存规则
                    </span>
                  )}
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() =>
                    setDraft({
                      key: tableKey(t),
                      seed: draftFromHeader(t.header, t.title),
                      header: t.header,
                    })
                  }
                >
                  生成规则草稿
                </Button>
              </div>
              <div className="mt-2 flex flex-wrap gap-1">
                {t.header.map((h, hi) => (
                  <span
                    key={hi}
                    className="bg-muted rounded px-1.5 py-0.5 text-xs"
                  >
                    {h}
                  </span>
                ))}
              </div>
            </div>
          ))}
          {tables.length === 0 && (
            <p className="text-muted-foreground py-6 text-center text-sm">
              没有未识别的表格。
            </p>
          )}
        </div>

        <div className="mt-6 border-t pt-4">
          <p className="text-muted-foreground mb-2 text-xs">
            为新表保存定位规则后,重解析本文档即可提取（OCR 缓存生效,秒级完成）。
          </p>
          <Button
            onClick={onReparse}
            disabled={reparsePending || remaining.length > 0}
          >
            {reparsePending ? "启动中…" : "重解析本文档"}
          </Button>
          {remaining.length > 0 && (
            <span className="text-muted-foreground ml-2 text-xs">
              （先为上方表格保存规则）
            </span>
          )}
        </div>
      </div>

      <SeedEditorDrawer
        open={draft !== null}
        seed={draft?.seed ?? null}
        headerCells={draft?.header}
        saving={saving}
        onClose={() => setDraft(null)}
        onSave={(s) => {
          if (draft) onCreateSeed(s, draft.key);
          setDraft(null);
        }}
      />
    </div>
  );
}
