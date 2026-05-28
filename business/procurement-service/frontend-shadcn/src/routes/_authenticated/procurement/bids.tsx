import { useState, useEffect, useCallback } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  RefreshCw,
  AlertCircle,
  FileX,
  CheckCircle2,
  XCircle,
  Clock,
  Eye,
  ShieldCheck,
} from 'lucide-react'
import { bidApi, type Bid } from '@/lib/api'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { Search } from '@/components/search'
import { ThemeSwitch } from '@/components/theme-switch'
import { ConfigDrawer } from '@/components/config-drawer'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { BidFormDialog } from '@/features/procurement/bid-form-dialog'
import { ComplianceCheckDialog } from '@/features/procurement/compliance-check-dialog'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import { Separator as SeparatorComponent } from '@/components/ui/separator'

export const Route = createFileRoute('/_authenticated/procurement/bids')({
  component: BidsPage,
})

const STATUS_VARIANT: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  draft: 'secondary',
  pending: 'default',
  submitted: 'default',
  approved: 'default',
  rejected: 'destructive',
  won: 'default',
  lost: 'secondary',
}

function ComplianceIcon({ passed }: { passed?: boolean }) {
  if (passed === true) return <CheckCircle2 className='h-4 w-4 text-green-600' />
  if (passed === false) return <XCircle className='h-4 w-4 text-red-600' />
  return <Clock className='h-4 w-4 text-muted-foreground' />
}

function BidsPage() {
  const [bids, setBids] = useState<Bid[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [keyword, setKeyword] = useState('')
  const [detailBid, setDetailBid] = useState<Bid | null>(null)
  const [detailSheetOpen, setDetailSheetOpen] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await bidApi.list({ limit: String(100) })
      setBids(data.bids)
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const formatDate = (date?: string) => date ? new Date(date).toLocaleDateString('zh-CN') : '—'
  const formatMoney = (amount?: number) => amount ? `¥${Number(amount).toLocaleString('zh-CN')}` : '—'

  return (
    <>
      <Header fixed>
        <Search className='me-auto' />
        <ThemeSwitch />
        <ConfigDrawer />
        <ProfileDropdown />
      </Header>

      <Main className='flex flex-1 flex-col gap-4 sm:gap-6'>
        <div className='flex flex-wrap items-end justify-between gap-2'>
          <div>
            <h2 className='text-2xl font-bold tracking-tight'>投标管理</h2>
            <p className='text-muted-foreground'>管理投标记录和报价</p>
          </div>
          <div className='flex items-center gap-2'>
            <div className='relative'>
              <Search className='absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground' />
              <Input
                placeholder='搜索投标...'
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                className='pl-9 w-48'
              />
            </div>
            <Button variant='outline' size='icon' onClick={load} disabled={loading}>
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            </Button>
            <BidFormDialog onSuccess={load} />
          </div>
        </div>
        <Separator className='shadow-sm' />

        {error && (
          <div className='flex items-center gap-2 rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive'>
            <AlertCircle className='h-4 w-4 shrink-0' />
            {error}
            <button onClick={load} className='underline ml-auto'>重试</button>
          </div>
        )}

        {loading ? (
          <div className='space-y-3'>
            {Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className='h-12 w-full' />)}
          </div>
        ) : bids.length === 0 ? (
          <div className='flex flex-col items-center justify-center py-16 text-muted-foreground'>
            <FileX className='h-12 w-12 mb-4 opacity-20' />
            <p className='text-sm'>暂无投标记录</p>
          </div>
        ) : (
          <div className='rounded-lg border overflow-hidden'>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>投标编号</TableHead>
                  <TableHead>投标报价</TableHead>
                  <TableHead>技术得分</TableHead>
                  <TableHead>商务得分</TableHead>
                  <TableHead>综合得分</TableHead>
                  <TableHead>排名</TableHead>
                  <TableHead>合规检查</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead className="w-[150px]">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {bids.map((b) => (
                  <TableRow key={b.id} className='hover:bg-muted/50 transition-colors'>
                    <TableCell>{b.bid_no}</TableCell>
                    <TableCell>{formatMoney(b.bid_price)}</TableCell>
                    <TableCell>{b.technical_score?.toFixed(2) ?? '—'}</TableCell>
                    <TableCell>{b.commercial_score?.toFixed(2) ?? '—'}</TableCell>
                    <TableCell>{b.total_score?.toFixed(2) ?? '—'}</TableCell>
                    <TableCell>{b.ranking ? `#${b.ranking}` : '—'}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <ComplianceIcon passed={b.compliance_check_passed} />
                        {b.compliance_issues && b.compliance_issues.length > 0 && (
                          <span className="text-xs text-muted-foreground">
                            ({b.compliance_issues.length}项)
                          </span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell><Badge variant={STATUS_VARIANT[b.status] ?? 'secondary'} className='capitalize'>{b.status}</Badge></TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          onClick={() => { setDetailBid(b); setDetailSheetOpen(true) }}
                        >
                          <Eye className="h-4 w-4" />
                        </Button>
                        <ComplianceCheckDialog bid={b} onSuccess={load}>
                          <Button variant="ghost" size="icon" className="h-8 w-8">
                            <ShieldCheck className="h-4 w-4" />
                          </Button>
                        </ComplianceCheckDialog>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Main>

      <Sheet open={detailSheetOpen} onOpenChange={setDetailSheetOpen}>
        <SheetContent className="sm:max-w-[500px] overflow-y-auto">
          <SheetHeader>
            <SheetTitle>投标详情</SheetTitle>
            <SheetDescription>
              {detailBid ? `投标编号：${detailBid.bid_no}` : '加载中...'}
            </SheetDescription>
          </SheetHeader>

          {detailBid && (
            <div className="mt-6 space-y-6">
              <div className="space-y-4">
                <div>
                  <h3 className="text-lg font-semibold">投标编号：{detailBid.bid_no}</h3>
                  <div className="flex items-center gap-2 mt-2 flex-wrap">
                    <Badge variant={STATUS_VARIANT[detailBid.status] ?? 'secondary'}>
                      {detailBid.status}
                    </Badge>
                    <div className="flex items-center gap-1">
                      <ComplianceIcon passed={detailBid.compliance_check_passed} />
                      <span className="text-sm">
                        {detailBid.compliance_check_passed === true ? '合规' :
                          detailBid.compliance_check_passed === false ? '不合规' : '待检查'}
                      </span>
                    </div>
                  </div>
                </div>

                <SeparatorComponent />

                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="text-muted-foreground">投标报价</p>
                    <p className="font-medium text-lg">{formatMoney(detailBid.bid_price)}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">综合得分</p>
                    <p className="font-medium text-lg">{detailBid.total_score?.toFixed(2) ?? '—'}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">技术得分</p>
                    <p className="font-medium">{detailBid.technical_score?.toFixed(2) ?? '—'}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">商务得分</p>
                    <p className="font-medium">{detailBid.commercial_score?.toFixed(2) ?? '—'}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">排名</p>
                    <p className="font-medium">{detailBid.ranking ? `#${detailBid.ranking}` : '—'}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">提交时间</p>
                    <p className="font-medium">{formatDate(detailBid.submitted_at)}</p>
                  </div>
                </div>

                {detailBid.compliance_issues && detailBid.compliance_issues.length > 0 && (
                  <>
                    <SeparatorComponent />
                    <div>
                      <p className="text-muted-foreground mb-2">合规问题：</p>
                      <ul className="text-sm space-y-1 list-disc list-inside">
                        {detailBid.compliance_issues.map((issue, index) => (
                          <li key={index} className="text-destructive">{String(issue)}</li>
                        ))}
                      </ul>
                    </div>
                  </>
                )}

                {detailBid.technical_proposal_url && (
                  <>
                    <SeparatorComponent />
                    <div>
                      <p className="text-muted-foreground mb-1">技术方案</p>
                      <a
                        href={detailBid.technical_proposal_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm text-blue-600 hover:underline"
                      >
                        查看技术方案
                      </a>
                    </div>
                  </>
                )}

                <SeparatorComponent />

                <div className="text-xs text-muted-foreground space-y-1">
                  <p>创建时间：{formatDate(detailBid.created_at)}</p>
                  <p>更新时间：{formatDate(detailBid.updated_at)}</p>
                </div>
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </>
  )
}
