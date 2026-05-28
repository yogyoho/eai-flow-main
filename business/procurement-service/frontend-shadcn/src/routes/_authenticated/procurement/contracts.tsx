import { useState, useEffect, useCallback } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { Button } from '@/components/ui/button'
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
  Plus,
  AlertCircle,
  FileX,
  AlertTriangle,
} from 'lucide-react'
import { contractApi, type Contract } from '@/lib/api'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { Search } from '@/components/search'
import { ThemeSwitch } from '@/components/theme-switch'
import { ConfigDrawer } from '@/components/config-drawer'
import { ProfileDropdown } from '@/components/profile-dropdown'

export const Route = createFileRoute('/_authenticated/procurement/contracts')({
  component: ContractsPage,
})

const STATUS_VARIANT: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  draft: 'secondary',
  pending: 'default',
  signed: 'default',
  active: 'default',
  completed: 'default',
  terminated: 'destructive',
  disputed: 'destructive',
}

const RISK_VARIANT: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  low: 'default',
  medium: 'default',
  high: 'destructive',
}

function ContractsPage() {
  const [contracts, setContracts] = useState<Contract[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await contractApi.list({ limit: String(100) })
      setContracts(data.contracts)
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
            <h2 className='text-2xl font-bold tracking-tight'>合同管理</h2>
            <p className='text-muted-foreground'>管理采购合同</p>
          </div>
          <div className='flex items-center gap-2'>
            <Button variant='outline' size='icon' onClick={load} disabled={loading}>
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            </Button>
            <Button size='sm'>
              <Plus className='h-4 w-4 mr-1' />
              新建合同
            </Button>
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
        ) : contracts.length === 0 ? (
          <div className='flex flex-col items-center justify-center py-16 text-muted-foreground'>
            <FileX className='h-12 w-12 mb-4 opacity-20' />
            <p className='text-sm'>暂无合同记录</p>
          </div>
        ) : (
          <div className='rounded-lg border overflow-hidden'>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>合同编号</TableHead>
                  <TableHead>合同名称</TableHead>
                  <TableHead>合同金额</TableHead>
                  <TableHead>风险等级</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>签订日期</TableHead>
                  <TableHead>到期日期</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {contracts.map((c) => (
                  <TableRow key={c.id} className='hover:bg-muted/50 transition-colors'>
                    <TableCell>{c.contract_no}</TableCell>
                    <TableCell>{c.title}</TableCell>
                    <TableCell>{formatMoney(c.total_price)}</TableCell>
                    <TableCell>
                      {c.risk_level ? (
                        <Badge variant={RISK_VARIANT[c.risk_level] ?? 'secondary'} className='capitalize gap-1'>
                          {c.risk_level === 'high' && <AlertTriangle className='h-3 w-3' />}
                          {c.risk_level}
                        </Badge>
                      ) : '—'}
                    </TableCell>
                    <TableCell><Badge variant={STATUS_VARIANT[c.status] ?? 'secondary'} className='capitalize'>{c.status}</Badge></TableCell>
                    <TableCell>{formatDate(c.sign_date)}</TableCell>
                    <TableCell>{formatDate(c.end_date)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Main>
    </>
  )
}
