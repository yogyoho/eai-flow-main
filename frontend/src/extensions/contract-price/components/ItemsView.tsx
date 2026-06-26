"use client";

import { AlertTriangle, Crosshair, PackageSearch, RefreshCw, Search } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { TracebackDrawer } from "@/extensions/contract-price/components/TracebackDrawer";
import { EmptyRow, PageHeader } from "@/extensions/contract-price/components/PageHeader";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/extensions/contract-price/components/ui/table";
import type { CpaItem } from "@/extensions/contract-price/types";
import { useItems, useUpdateItem } from "@/extensions/contract-price/hooks";

const STATUS_TONE: Record<string, string> = {
  ok: "text-emerald-600 border-emerald-500/30 bg-emerald-500/5",
  needs_review: "text-amber-600 border-amber-500/30 bg-amber-500/5",
  corrected: "text-blue-600 border-blue-500/30 bg-blue-500/5",
};
const STATUS_LABEL: Record<string, string> = {
  ok: "已校验",
  needs_review: "待核验",
  corrected: "已修正",
};

export function ItemsView() {
  const [keyword, setKeyword] = useState("");
  const [applied, setApplied] = useState("");
  const [onlyOutliers, setOnlyOutliers] = useState(false);
  const [onlyReview, setOnlyReview] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [priceInput, setPriceInput] = useState("");
  const [note, setNote] = useState("");
  const [trace, setTrace] = useState<CpaItem | null>(null);

  const { data, isLoading, isFetching, refetch } = useItems({
    goods_name: applied || undefined,
    only_outliers: onlyOutliers,
    limit: 100,
  });
  const updateItem = useUpdateItem();

  const raw = data?.items ?? [];
  const items = onlyReview ? raw.filter((i) => i.validation_status === "needs_review") : raw;

  return (
    <div className="space-y-6 p-8">
      <PageHeader
        title="分项明细"
        description="每条货物的单价与参数。待核验项(OCR 数字粘连/量级异常)需用溯源对照原文后修正。"
        icon={<PackageSearch className="w-4 h-4" />}
        actions={
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`} />
            刷新
          </Button>
        }
      />

      <Card>
        <CardContent className="space-y-4 p-6">
          <div className="flex flex-wrap items-center gap-2">
            <form
              className="flex items-center gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                setApplied(keyword);
              }}
            >
              <div className="relative max-w-sm">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={keyword}
                  onChange={(e) => setKeyword(e.target.value)}
                  placeholder="搜索货物名称"
                  className="pl-9"
                />
              </div>
              <Button type="submit" size="sm">
                搜索
              </Button>
            </form>
            <label className="flex items-center gap-1.5 text-sm text-muted-foreground">
              <input
                type="checkbox"
                checked={onlyOutliers}
                onChange={(e) => setOnlyOutliers(e.target.checked)}
                className="accent-primary"
              />
              仅看异常价格
            </label>
            <label className="flex items-center gap-1.5 text-sm text-muted-foreground">
              <input
                type="checkbox"
                checked={onlyReview}
                onChange={(e) => setOnlyReview(e.target.checked)}
                className="accent-amber-500"
              />
              仅看待核验
            </label>
          </div>

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>货物名称</TableHead>
                <TableHead>规格</TableHead>
                <TableHead>来源合同</TableHead>
                <TableHead>状态</TableHead>
                <TableHead className="text-right">单价</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <EmptyRow colSpan={6}>加载中…</EmptyRow>
              ) : items.length === 0 ? (
                <EmptyRow colSpan={6}>暂无明细。</EmptyRow>
              ) : (
                items.map((item) => (
                  <TableRow key={item.id} className={item.is_outlier ? "bg-destructive/10" : ""}>
                    <TableCell className="font-medium">
                      {item.is_outlier ? (
                        <span className="inline-flex items-center gap-1">
                          <AlertTriangle className="h-3.5 w-3.5 text-destructive" />
                          {item.goods_name}
                        </span>
                      ) : (
                        item.goods_name
                      )}
                    </TableCell>
                    <TableCell className="text-muted-foreground">{item.spec_model ?? "—"}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {item.source_contract_no ?? "—"}
                    </TableCell>
                    <TableCell>
                      <span
                        className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[11px] font-medium ${
                          STATUS_TONE[item.validation_status] ?? STATUS_TONE.ok
                        }`}
                      >
                        {STATUS_LABEL[item.validation_status] ?? item.validation_status}
                        {item.confidence != null && (
                          <span className="ml-1 opacity-60">{(item.confidence * 100).toFixed(0)}%</span>
                        )}
                      </span>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {editingId === item.id ? (
                        <Input
                          type="number"
                          value={priceInput}
                          onChange={(e) => setPriceInput(e.target.value)}
                          className="h-8 w-28 text-right"
                        />
                      ) : item.unit_price == null ? (
                        <span className="text-amber-600">待核验</span>
                      ) : item.is_outlier ? (
                        <span className="text-destructive">{item.unit_price.toLocaleString()}</span>
                      ) : (
                        item.unit_price.toLocaleString()
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      {editingId === item.id ? (
                        <div className="flex items-center justify-end gap-1">
                          <Input
                            value={note}
                            onChange={(e) => setNote(e.target.value)}
                            placeholder="修正原因"
                            className="h-8 w-32"
                          />
                          <Button
                            size="sm"
                            onClick={async () => {
                              await updateItem.mutateAsync({
                                id: item.id,
                                body: { unit_price: Number(priceInput), note: note || undefined },
                              });
                              setEditingId(null);
                              setNote("");
                            }}
                          >
                            保存
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => setEditingId(null)}>
                            取消
                          </Button>
                        </div>
                      ) : (
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => {
                              setEditingId(item.id);
                              setPriceInput(String(item.unit_price ?? ""));
                            }}
                          >
                            修正
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={item.source_page == null}
                            title={item.source_page == null ? "无溯源坐标" : "溯源到原文"}
                            onClick={() => setTrace(item)}
                          >
                            <Crosshair className="h-3.5 w-3.5 text-rose-500" />
                            溯源
                          </Button>
                        </div>
                      )}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <TracebackDrawer
        docId={trace?.document_id ?? null}
        page={trace?.source_page ?? null}
        bbox={trace?.source_bbox ?? null}
        onClose={() => setTrace(null)}
      />
    </div>
  );
}
