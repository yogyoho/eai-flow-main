"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Delete, FileUp, PackageSearch, RefreshCw, Search } from "lucide-react";
import { useRef, useState } from "react";

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
import { useDocuments, useUploadDocument } from "@/extensions/contract-price/hooks";

const statusTone: Record<string, string> = {
  parsed: "text-emerald-600",
  pending: "text-muted-foreground",
  failed: "text-destructive",
  needs_review: "text-amber-600",
};

function formatDate(s: string | null): string {
  if (!s) return "—";
  return new Date(s).toLocaleString("zh-CN", { hour12: false });
}

export function ContractsView() {
  const [keyword, setKeyword] = useState("");
  const [applied, setApplied] = useState("");
  const qc = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const upload = useUploadDocument();

  const { data, isLoading, isFetching, refetch } = useDocuments({
    keyword: applied || undefined,
    limit: 50,
  });

  const docs = data?.items ?? [];

  return (
    <div className="space-y-6 p-8">
      <PageHeader
        title="合同文档"
        description="上传合同扫描件(PDF/DOCX),存入独立 MinIO bucket。点总览「立即分析」触发 OCR 提取。"
        icon={<PackageSearch className="w-4 h-4" />}
        actions={
          <div className="flex items-center gap-2">
            <input
              ref={fileInput}
              type="file"
              accept=".pdf,.docx"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) upload.mutate(f);
                e.target.value = "";
              }}
            />
            <Button size="sm" onClick={() => fileInput.current?.click()} disabled={upload.isPending}>
              <FileUp className="h-4 w-4" />
              {upload.isPending ? "上传中…" : "上传合同"}
            </Button>
            <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
              <RefreshCw className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`} />
              刷新
            </Button>
          </div>
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
                <TableHead>文件名</TableHead>
                <TableHead>供应商</TableHead>
                <TableHead>类型</TableHead>
                <TableHead>提取健康度</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>解析时间</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <EmptyRow colSpan={7}>加载中…</EmptyRow>
              ) : docs.length === 0 ? (
                <EmptyRow colSpan={7}>暂无合同。点右上「上传合同」或总览页「立即分析」。</EmptyRow>
              ) : (
                docs.map((doc) => {
                  const meta = doc.parse_meta as
                    | { tables_found?: number; goods_tables?: number; rows_extracted?: number }
                    | null;
                  return (
                    <TableRow key={doc.id} className="group">
                      <TableCell className="font-medium max-w-[220px] truncate" title={doc.file_name}>
                        {doc.file_name}
                      </TableCell>
                      <TableCell>{doc.supplier ?? "—"}</TableCell>
                      <TableCell className="uppercase text-muted-foreground">{doc.file_type}</TableCell>
                      <TableCell className="text-muted-foreground tabular-nums">
                        {meta ? (
                          <span className="text-xs">
                            <span className="text-foreground font-medium">{meta.goods_tables ?? 0}</span> 货物表
                            <span className="mx-1 opacity-40">/</span>
                            {meta.tables_found ?? 0} 表
                            <span className="mx-1 opacity-40">/</span>
                            {meta.rows_extracted ?? 0} 行
                          </span>
                        ) : (
                          "—"
                        )}
                      </TableCell>
                      <TableCell className={statusTone[doc.parse_status] ?? ""}>{doc.parse_status}</TableCell>
                      <TableCell className="whitespace-nowrap">{formatDate(doc.parsed_at)}</TableCell>
                      <TableCell className="text-right">
                        <Button
                          size="icon"
                          variant="ghost"
                          className="opacity-0 transition-opacity group-hover:opacity-100 text-destructive hover:text-destructive"
                          title="删除合同及其分项"
                          onClick={async () => {
                            if (!confirm(`删除合同 ${doc.file_name} 及其分项？`)) return;
                            await contractPriceApi.deleteDocument(doc.id);
                            void qc.invalidateQueries({ queryKey: ["cpa"] });
                          }}
                        >
                          <Delete className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
