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
import { planApi, type TenderPlan } from '@/lib/api'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { Search } from '@/components/search'
import { ThemeSwitch } from '@/components/theme-switch'
import { ConfigDrawer } from '@/components/config-drawer'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { PlanFormDialog } from '@/features/procurement/plan-form-dialog'
import { PlanDetailSheet } from '@/features/procurement/plan-detail-sheet'

export const Route = createFileRoute('/_authenticated/procurement/plans')({
  component: PlansPage,
})

const STATUS_VARIANT: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  draft: 'secondary',
  pending: 'default',
  submitted: 'default',
  published: 'default',
  bidding: 'default',
  evaluating: 'secondary',
  completed: 'default',
  rejected: 'destructive',
}

function StatusBadge({ status }: { status: string }) {
  return <Badge variant={STATUS_VARIANT[status] ?? 'secondary'} className='capitalize'>{status}</Badge>
}

function PlansPage() {
  const [plans, setPlans] = useState<TenderPlan[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [keyword, setKeyword] = useState('')
  const [detailPlanId, setDetailPlanId] = useState<string | null>(null)
  const [detailSheetOpen, setDetailSheetOpen] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params: Record<string, string> = {}
      if (keyword) params.keyword = keyword
      params.limit = '100'
      const data = await planApi.list(params)
      setPlans(data.plans)
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [keyword])

  useEffect(() => { load() }, [load])

  const formatDate = (date: string) => new Date(date).toLocaleDateString('zh-CN')
  const formatMoney = (amount?: number) => amount ? `¥${Number(amount).toLocaleString('zh-CN')}` : '—'

  const openDetailSheet = (plan: TenderPlan) => {
    setDetailPlanId(plan.id)
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
            <h2 className='text-2xl font-bold tracking-tight'>招标计划管理</h2>
            <p className='text-muted-foreground'>管理招标计划列表</p>
          </div>
          <div className='flex items-center gap-2'>
            <div className='relative'>
              <SearchIcon className='absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground' />
              <Input
                placeholder='搜索计划...'
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                className='pl-9 w-48'
              />
            </div>
            <Button variant='outline' size='icon' onClick={load} disabled={loading}>
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            </Button>
            <PlanFormDialog onSuccess={load} />
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
        ) : plans.length === 0 ? (
          <div className='flex flex-col items-center justify-center py-16 text-muted-foreground'>
            <FileX className='h-12 w-12 mb-4 opacity-20' />
            <p className='text-sm'>暂无招标计划</p>
          </div>
        ) : (
          <div className='rounded-lg border overflow-hidden'>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>计划编号</TableHead>
                  <TableHead>计划名称</TableHead>
                  <TableHead>采购类型</TableHead>
                  <TableHead>需求部门</TableHead>
                  <TableHead>预算金额</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>创建时间</TableHead>
                  <TableHead className="w-[100px]">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {plans.map((p) => (
                  <TableRow key={p.id} className='hover:bg-muted/50 transition-colors'>
                    <TableCell>{p.plan_no}</TableCell>
                    <TableCell>{p.title}</TableCell>
                    <TableCell>{p.procurement_type}</TableCell>
                    <TableCell>{p.dept_name ?? '—'}</TableCell>
                    <TableCell>{formatMoney(p.budget)}</TableCell>
                    <TableCell><StatusBadge status={p.status} /></TableCell>
                    <TableCell>{formatDate(p.created_at)}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => openDetailSheet(p)}>
                          <Eye className="h-4 w-4" />
                        </Button>
                        <PlanFormDialog plan={p} onSuccess={load}>
                          <Button variant="ghost" size="icon" className="h-8 w-8">
                            <Pencil className="h-4 w-4" />
                          </Button>
                        </PlanFormDialog>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Main>

      <PlanDetailSheet
        planId={detailPlanId}
        open={detailSheetOpen}
        onOpenChange={setDetailSheetOpen}
      />
    </>
  )
}
