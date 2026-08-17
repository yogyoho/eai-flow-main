"use client";

/**
 * 客户管理(D3: master/alias 归并)。
 * - 列表:标准名 / 别名 / 状态 / 文档数 / 来源
 * - 新建 / 编辑(标准名 + 别名)
 * - 认领:把一个 OCR 脏客户名挂到已有客户(追加别名)
 * - 合并:多选客户 → 合并到其中一个(文档+明细 customer_id 重指)
 * - 解析预览:只读,一批脏名能匹配到哪些客户
 */
import { GitMerge, Plus, RefreshCw, Search, Tags, Wand2 } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  EmptyRow,
  PageHeader,
} from "@/extensions/spare-parts/components/PageHeader";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/extensions/spare-parts/components/ui/table";
import {
  useClaimCustomer,
  useCreateCustomer,
  useCustomers,
  useMergeCustomers,
  useResolveCustomers,
  useUpdateCustomer,
} from "@/extensions/spare-parts/hooks";
import type { CspCustomer } from "@/extensions/spare-parts/types";

const STATUS_TONE: Record<string, string> = {
  active: "text-emerald-600 border-emerald-500/30 bg-emerald-500/5",
  pending: "text-amber-600 border-amber-500/30 bg-amber-500/5",
  merged: "text-muted-foreground border-border bg-muted/40 line-through",
};

/** 把多行文本拆成去重的别名列表(去空、去重、trim)。 */
function parseAliases(text: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of text.split("\n")) {
    const v = raw.trim();
    if (v && !seen.has(v.toLowerCase())) {
      seen.add(v.toLowerCase());
      out.push(v);
    }
  }
  return out;
}

export function CustomersView() {
  const [keyword, setKeyword] = useState("");
  const [status, setStatus] = useState<string>("");

  // ponytail: 主数据表(客户)通常只有几十行,单页 200 足够,先不做分页
  const { data, isLoading, isFetching, refetch } = useCustomers({
    keyword: keyword || undefined,
    status: status || undefined,
    limit: 200,
  });
  const customers = useMemo(() => data?.items ?? [], [data]);

  // --- 多选合并 ---
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [mergeTarget, setMergeTarget] = useState<string>("");
  const mergeMut = useMergeCustomers();

  // --- 新建 / 编辑(共用表单) ---
  type EditState = { id: string | null; canonical: string; aliases: string };
  const [editOpen, setEditOpen] = useState(false);
  const [edit, setEdit] = useState<EditState>({
    id: null,
    canonical: "",
    aliases: "",
  });
  const createMut = useCreateCustomer();
  const updateMut = useUpdateCustomer();

  // --- 认领 ---
  const [claim, setClaim] = useState<{
    id: string;
    canonical: string;
    raw: string;
  } | null>(null);
  const claimMut = useClaimCustomer();

  // --- 解析预览 ---
  const [resolveOpen, setResolveOpen] = useState(false);
  const [resolveText, setResolveText] = useState("");
  const resolveMut = useResolveCustomers();

  const custMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const c of customers) m.set(c.id, c.canonical_name);
    return m;
  }, [customers]);

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const openCreate = () => {
    setEdit({ id: null, canonical: "", aliases: "" });
    setEditOpen(true);
  };
  const openEdit = (c: CspCustomer) => {
    setEdit({
      id: c.id,
      canonical: c.canonical_name,
      aliases: c.aliases.join("\n"),
    });
    setEditOpen(true);
  };

  const submitEdit = () => {
    const canonical = edit.canonical.trim();
    if (!canonical) return;
    const aliases = parseAliases(edit.aliases);
    if (edit.id) {
      updateMut.mutate({
        id: edit.id,
        body: { canonical_name: canonical, aliases },
      });
    } else {
      createMut.mutate({ canonical_name: canonical, aliases });
    }
    setEditOpen(false);
  };

  const submitMerge = () => {
    if (!mergeTarget) return;
    const source_ids = [...selected].filter((id) => id !== mergeTarget);
    if (source_ids.length === 0) return;
    mergeMut.mutate(
      { source_ids, target_id: mergeTarget },
      {
        onSettled: () => {
          setSelected(new Set());
          setMergeTarget("");
        },
      },
    );
  };

  const submitClaim = () => {
    if (!claim?.raw.trim()) return;
    claimMut.mutate(
      { id: claim.id, raw_name: claim.raw.trim() },
      { onSettled: () => setClaim(null) },
    );
  };

  const submitResolve = () => {
    const names = parseAliases(resolveText);
    if (names.length === 0) return;
    resolveMut.mutate(names);
  };

  const selectedCustomers = customers.filter((c) => selected.has(c.id));
  const resolveResults = resolveMut.data ?? [];

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4 p-6">
      <PageHeader
        icon={<Tags className="h-5 w-5" />}
        title="客户管理"
        description="跨客户备品备件比价的客户主数据:维护标准名与别名,认领 OCR 脏名,合并重复客户。"
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => refetch()}>
              <RefreshCw
                className={`mr-1.5 h-4 w-4 ${isFetching ? "animate-spin" : ""}`}
              />
              刷新
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setResolveOpen(true)}
            >
              <Wand2 className="mr-1.5 h-4 w-4" />
              解析预览
            </Button>
            <Button size="sm" onClick={openCreate}>
              <Plus className="mr-1.5 h-4 w-4" />
              新建客户
            </Button>
          </>
        }
      />

      {/* 过滤 */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative w-72">
          <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 h-4 w-4 -translate-y-1/2" />
          <Input
            placeholder="搜索标准名或别名…"
            className="pl-8"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
          />
        </div>
        <Select
          value={status || "all"}
          onValueChange={(v) => setStatus(v === "all" ? "" : v)}
        >
          <SelectTrigger className="w-40">
            <SelectValue placeholder="状态" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部状态</SelectItem>
            <SelectItem value="active">active</SelectItem>
            <SelectItem value="pending">pending</SelectItem>
            <SelectItem value="merged">merged</SelectItem>
          </SelectContent>
        </Select>
        <span className="text-muted-foreground text-sm">
          共 {customers.length} 个客户
        </span>
      </div>

      {/* 合并栏(选中 ≥2 时浮现) */}
      {selectedCustomers.length >= 2 && (
        <Card className="border-blue-200 bg-blue-50/50">
          <CardContent className="flex flex-wrap items-center gap-2 p-3">
            <GitMerge className="h-4 w-4 text-blue-600" />
            <span className="text-sm">已选 {selected.size} 个客户,合并到:</span>
            <Select value={mergeTarget} onValueChange={setMergeTarget}>
              <SelectTrigger className="w-60">
                <SelectValue placeholder="选择目标客户" />
              </SelectTrigger>
              <SelectContent>
                {selectedCustomers.map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    {c.canonical_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              size="sm"
              disabled={!mergeTarget || mergeMut.isPending}
              onClick={submitMerge}
            >
              {mergeMut.isPending ? "合并中…" : "合并"}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setSelected(new Set())}
            >
              取消
            </Button>
            {mergeMut.error ? (
              <span className="text-destructive text-xs">
                合并失败:已重指文档与明细
              </span>
            ) : null}
          </CardContent>
        </Card>
      )}

      {/* 列表 */}
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-10" />
                <TableHead>标准名</TableHead>
                <TableHead>别名</TableHead>
                <TableHead className="w-24">状态</TableHead>
                <TableHead className="w-20 text-right">文档数</TableHead>
                <TableHead className="w-24">来源</TableHead>
                <TableHead className="w-32">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <EmptyRow colSpan={7}>加载中…</EmptyRow>
              ) : customers.length === 0 ? (
                <EmptyRow colSpan={7}>
                  暂无客户,先「新建客户」或上传文档后由管线自动认领
                </EmptyRow>
              ) : (
                customers.map((c) => (
                  <TableRow
                    key={c.id}
                    className={c.status === "merged" ? "opacity-50" : ""}
                  >
                    <TableCell>
                      {c.status !== "merged" ? (
                        <Checkbox
                          checked={selected.has(c.id)}
                          onCheckedChange={() => toggle(c.id)}
                        />
                      ) : null}
                    </TableCell>
                    <TableCell className="font-medium">
                      {c.canonical_name}
                    </TableCell>
                    <TableCell className="text-muted-foreground max-w-md text-xs">
                      {c.aliases.length > 0 ? c.aliases.join("、") : "—"}
                    </TableCell>
                    <TableCell>
                      <span
                        className={`inline-block rounded border px-1.5 py-0.5 text-xs ${STATUS_TONE[c.status] ?? STATUS_TONE.pending}`}
                      >
                        {c.status}
                      </span>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {c.doc_count}
                    </TableCell>
                    <TableCell className="text-muted-foreground text-xs">
                      {c.source ?? "—"}
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => openEdit(c)}
                        >
                          编辑
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() =>
                            setClaim({
                              id: c.id,
                              canonical: c.canonical_name,
                              raw: "",
                            })
                          }
                        >
                          认领
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* 新建 / 编辑 */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{edit.id ? "编辑客户" : "新建客户"}</DialogTitle>
            <DialogDescription>
              标准名为客户唯一标识;别名每行一个,匹配时大小写不敏感。OCR
              解析出的脏名若命中任一别名即归到该客户。
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-3 py-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="cust-canonical">标准名</Label>
              <Input
                id="cust-canonical"
                value={edit.canonical}
                onChange={(e) =>
                  setEdit({ ...edit, canonical: e.target.value })
                }
                placeholder="如:华东医药股份有限公司"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="cust-aliases">别名(每行一个)</Label>
              <Textarea
                id="cust-aliases"
                rows={5}
                value={edit.aliases}
                onChange={(e) => setEdit({ ...edit, aliases: e.target.value })}
                placeholder={"如:\n华东医药\n华东"}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setEditOpen(false)}>
              取消
            </Button>
            <Button
              onClick={submitEdit}
              disabled={
                !edit.canonical.trim() ||
                createMut.isPending ||
                updateMut.isPending
              }
            >
              {edit.id ? "保存" : "创建"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 认领 */}
      <Dialog open={!!claim} onOpenChange={(o) => !o && setClaim(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>认领脏客户名 → {claim?.canonical}</DialogTitle>
            <DialogDescription>
              把一个 OCR 识别出的脏客户名挂到「{claim?.canonical}
              」(作为新别名追加,去重)。已归到该客户的文档/明细不受影响。
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-1.5 py-2">
            <Label htmlFor="claim-raw">脏客户名</Label>
            <Input
              id="claim-raw"
              value={claim?.raw ?? ""}
              onChange={(e) =>
                setClaim({
                  ...(claim as { id: string; canonical: string; raw: string }),
                  raw: e.target.value,
                })
              }
              placeholder="如:华东医药股份有限公哥"
            />
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setClaim(null)}>
              取消
            </Button>
            <Button
              onClick={submitClaim}
              disabled={!claim?.raw.trim() || claimMut.isPending}
            >
              认领
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 解析预览(只读) */}
      <Dialog open={resolveOpen} onOpenChange={setResolveOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>解析预览(只读)</DialogTitle>
            <DialogDescription>
              粘贴一批 OCR
              脏客户名(每行一个),预览它们能匹配到哪些已有客户。未匹配的会显示「未匹配」(将来由管线标为
              pending,不会丢弃)。
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2 py-2">
            <Textarea
              rows={5}
              value={resolveText}
              onChange={(e) => setResolveText(e.target.value)}
              placeholder={"每行一个脏客户名…"}
            />
            <Button
              size="sm"
              className="self-start"
              onClick={submitResolve}
              disabled={resolveMut.isPending}
            >
              {resolveMut.isPending ? "解析中…" : "预览匹配"}
            </Button>
          </div>
          {resolveResults.length > 0 ? (
            <div className="max-h-64 overflow-auto rounded border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>脏名</TableHead>
                    <TableHead>匹配客户</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {resolveResults.map((r) => (
                    <TableRow key={r.raw_name}>
                      <TableCell className="text-sm">{r.raw_name}</TableCell>
                      <TableCell className="text-sm">
                        {r.customer_id ? (
                          <span className="text-emerald-600">
                            {custMap.get(r.customer_id) ??
                              r.customer_id.slice(0, 8)}
                          </span>
                        ) : (
                          <span className="text-amber-600">未匹配</span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : null}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setResolveOpen(false)}>
              关闭
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
