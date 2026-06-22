"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Delete, PackageSearch, RefreshCw, Search } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { contractPriceApi } from "@/extensions/contract-price/api";
import { EmptyRow, PageHeader } from "@/extensions/contract-price/components/PageHeader";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/extensions/contract-price/components/ui/table";
import { useDocuments } from "@/extensions/contract-price/hooks";

const statusTone: Record<string, string> = {
  parsed: "text-success",
  pending: "text-muted-foreground",
  failed: "text-destructive",
};

function formatDate(s: string | null): string {
  if (!s) return "—";
  return new Date(s).toLocaleString("zh-CN", { hour12: false });
}

export function ContractsView() {
  const [keyword, setKeyword] = useState("");
  const [applied, setApplied] = useState("");
  const qc = useQueryClient();
  const { data, isLoading, isFetching, refetch } = useDocuments({
    keyword: applied || undefined,
    limit: 50,
  });

  const docs = data?.items ?? [];

  return (
    <div className="space-y-6 p-8">
      <PageHeader
        title="合同缓存清单"
        description="从 RAGFlow 同步并解析的合同文档。删除将级联清除其分项明细。"
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
          <form
            className="flex items-center gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              setApplied(keyword);
            }}
          >
            <div className="relative max-w-sm flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                placeholder="搜索合同号 / 供应商"
                className="pl-9"
              />
            </div>
            <Button type="submit" size="sm">
              搜索
            </Button>
          </form>

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>合同号</TableHead>
                <TableHead>供应商</TableHead>
                <TableHead>解析模式</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>解析时间</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <EmptyRow colSpan={6}>加载中…</EmptyRow>
              ) : docs.length === 0 ? (
                <EmptyRow colSpan={6}>暂无合同缓存。点击总览页「立即分析」开始同步。</EmptyRow>
              ) : (
                docs.map((doc) => (
                  <TableRow key={doc.id} className="group">
                    <TableCell className="font-medium">{doc.contract_no ?? doc.ragflow_doc_id}</TableCell>
                    <TableCell>{doc.supplier ?? "—"}</TableCell>
                    <TableCell>{doc.parse_mode}</TableCell>
                    <TableCell className={statusTone[doc.parse_status] ?? ""}>
                      {doc.parse_status}
                    </TableCell>
                    <TableCell className="whitespace-nowrap">{formatDate(doc.parsed_at)}</TableCell>
                    <TableCell className="text-right">
                      <Button
                        size="icon"
                        variant="ghost"
                        className="opacity-0 transition-opacity group-hover:opacity-100 text-destructive hover:text-destructive"
                        title="删除缓存"
                        onClick={async () => {
                          if (!confirm(`删除合同 ${doc.contract_no ?? doc.id} 及其分项？`)) return;
                          await contractPriceApi.deleteDocument(doc.id);
                          void qc.invalidateQueries({ queryKey: ["cpa"] });
                        }}
                      >
                        <Delete className="h-4 w-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
