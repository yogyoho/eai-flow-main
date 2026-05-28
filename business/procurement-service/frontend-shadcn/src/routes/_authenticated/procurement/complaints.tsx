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
  AlertCircle,
  FileX,
} from 'lucide-react'
import { complaintApi, type Complaint } from '@/lib/api'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { Search } from '@/components/search'
import { ThemeSwitch } from '@/components/theme-switch'
import { ConfigDrawer } from '@/components/config-drawer'
import { ProfileDropdown } from '@/components/profile-dropdown'

export const Route = createFileRoute('/_authenticated/procurement/complaints')({
  component: ComplaintsPage,
})

const STATUS_VARIANT: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  pending: 'default',
  processing: 'default',
  decided: 'default',
  rejected: 'destructive',
  withdrawn: 'secondary',
}

const PRIORITY_VARIANT: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  low: 'secondary',
  medium: 'default',
  high: 'destructive',
  urgent: 'destructive',
}

function ComplaintsPage() {
  const [complaints, setComplaints] = useState<Complaint[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await complaintApi.list({ limit: String(100) })
      setComplaints(data.complaints)
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const formatDate = (date: string) => new Date(date).toLocaleDateString('zh-CN')

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
            <h2 className='text-2xl font-bold tracking-tight'>投诉处理</h2>
            <p className='text-muted-foreground'>管理投标投诉和异议</p>
          </div>
          <div className='flex items-center gap-2'>
            <Button variant='outline' size='icon' onClick={load} disabled={loading}>
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
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
        ) : complaints.length === 0 ? (
          <div className='flex flex-col items-center justify-center py-16 text-muted-foreground'>
            <FileX className='h-12 w-12 mb-4 opacity-20' />
            <p className='text-sm'>暂无投诉记录</p>
          </div>
        ) : (
          <div className='rounded-lg border overflow-hidden'>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>投诉编号</TableHead>
                  <TableHead>投诉标题</TableHead>
                  <TableHead>投诉类型</TableHead>
                  <TableHead>优先级</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>提交人</TableHead>
                  <TableHead>提交时间</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {complaints.map((c) => (
                  <TableRow key={c.id} className='hover:bg-muted/50 transition-colors'>
                    <TableCell>{c.complaint_no}</TableCell>
                    <TableCell>{c.title}</TableCell>
                    <TableCell>{c.complaint_type}</TableCell>
                    <TableCell><Badge variant={PRIORITY_VARIANT[c.priority] ?? 'secondary'} className='capitalize'>{c.priority}</Badge></TableCell>
                    <TableCell><Badge variant={STATUS_VARIANT[c.status] ?? 'secondary'} className='capitalize'>{c.status}</Badge></TableCell>
                    <TableCell>{c.complainer_name ?? '—'}</TableCell>
                    <TableCell>{formatDate(c.created_at)}</TableCell>
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
