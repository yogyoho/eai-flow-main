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
  Search as SearchIcon,
  AlertCircle,
  FileX,
  Eye,
  Pencil,
} from 'lucide-react'
import { bidderApi, type Bidder } from '@/lib/api'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { Search } from '@/components/search'
import { ThemeSwitch } from '@/components/theme-switch'
import { ConfigDrawer } from '@/components/config-drawer'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { BidderFormDialog } from '@/features/procurement/bidder-form-dialog'
import { BidderDetailSheet } from '@/features/procurement/bidder-detail-sheet'

export const Route = createFileRoute('/_authenticated/procurement/bidders')({
  component: BiddersPage,
})

const STATUS_VARIANT: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  active: 'default',
  inactive: 'secondary',
  pending: 'default',
  suspended: 'destructive',
  approved: 'default',
  rejected: 'destructive',
}

function BiddersPage() {
  const [bidders, setBidders] = useState<Bidder[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [keyword, setKeyword] = useState('')
  const [detailBidderId, setDetailBidderId] = useState<string | null>(null)
  const [detailSheetOpen, setDetailSheetOpen] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params: Record<string, string> = {}
      if (keyword) params.keyword = keyword
      params.limit = '100'
      const data = await bidderApi.list(params)
      setBidders(data.bidders)
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [keyword])

  useEffect(() => { load() }, [load])

  const openDetailSheet = (bidder: Bidder) => {
    setDetailBidderId(bidder.id)
    setDetailSheetOpen(true)
  }

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
            <h2 className='text-2xl font-bold tracking-tight'>投标人库</h2>
            <p className='text-muted-foreground'>管理投标人信息</p>
          </div>
          <div className='flex items-center gap-2'>
            <div className='relative'>
              <SearchIcon className='absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground' />
              <Input
                placeholder='搜索投标人...'
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                className='pl-9 w-48'
              />
            </div>
            <Button variant='outline' size='icon' onClick={load} disabled={loading}>
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            </Button>
            <BidderFormDialog onSuccess={load} />
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
        ) : bidders.length === 0 ? (
          <div className='flex flex-col items-center justify-center py-16 text-muted-foreground'>
            <FileX className='h-12 w-12 mb-4 opacity-20' />
            <p className='text-sm'>暂无投标人数据</p>
          </div>
        ) : (
          <div className='rounded-lg border overflow-hidden'>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>企业名称</TableHead>
                  <TableHead>统一信用代码</TableHead>
                  <TableHead>地区</TableHead>
                  <TableHead>信用评级</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>联系人</TableHead>
                  <TableHead>联系电话</TableHead>
                  <TableHead className="w-[100px]">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {bidders.map((b) => (
                  <TableRow key={b.id} className='hover:bg-muted/50 transition-colors'>
                    <TableCell>{b.name}</TableCell>
                    <TableCell>{b.unified_credit_code ?? '—'}</TableCell>
                    <TableCell>{b.region ?? '—'}</TableCell>
                    <TableCell>{b.credit_rating ?? '—'}</TableCell>
                    <TableCell><Badge variant={STATUS_VARIANT[b.status] ?? 'secondary'} className='capitalize'>{b.status === 'active' ? '正常' : b.status}</Badge></TableCell>
                    <TableCell>{b.contact_person ?? '—'}</TableCell>
                    <TableCell>{b.phone ?? '—'}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => openDetailSheet(b)}>
                          <Eye className="h-4 w-4" />
                        </Button>
                        <BidderFormDialog bidder={b} onSuccess={load}>
                          <Button variant="ghost" size="icon" className="h-8 w-8">
                            <Pencil className="h-4 w-4" />
                          </Button>
                        </BidderFormDialog>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Main>

      <BidderDetailSheet
        bidderId={detailBidderId}
        open={detailSheetOpen}
        onOpenChange={setDetailSheetOpen}
      />
    </>
  )
}
