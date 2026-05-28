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
} from 'lucide-react'
import { venueApi, type VenueSpace } from '@/lib/api'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { Search } from '@/components/search'
import { ThemeSwitch } from '@/components/theme-switch'
import { ConfigDrawer } from '@/components/config-drawer'
import { ProfileDropdown } from '@/components/profile-dropdown'

export const Route = createFileRoute('/_authenticated/procurement/venues')({
  component: VenuesPage,
})

const STATUS_VARIANT: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  available: 'default',
  occupied: 'default',
  maintenance: 'destructive',
  reserved: 'secondary',
}

function VenuesPage() {
  const [spaces, setSpaces] = useState<VenueSpace[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await venueApi.list({ limit: String(100) })
      setSpaces(data.spaces)
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

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
            <h2 className='text-2xl font-bold tracking-tight'>场所工位管理</h2>
            <p className='text-muted-foreground'>管理开标评标场所和工位</p>
          </div>
          <div className='flex items-center gap-2'>
            <Button variant='outline' size='icon' onClick={load} disabled={loading}>
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            </Button>
            <Button size='sm'>
              <Plus className='h-4 w-4 mr-1' />
              新增工位
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
        ) : spaces.length === 0 ? (
          <div className='flex flex-col items-center justify-center py-16 text-muted-foreground'>
            <FileX className='h-12 w-12 mb-4 opacity-20' />
            <p className='text-sm'>暂无场所工位</p>
          </div>
        ) : (
          <div className='rounded-lg border overflow-hidden'>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>场所名称</TableHead>
                  <TableHead>工位编号</TableHead>
                  <TableHead>楼层</TableHead>
                  <TableHead>容量</TableHead>
                  <TableHead>设备</TableHead>
                  <TableHead>小时费用</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>描述</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {spaces.map((v) => (
                  <TableRow key={v.id} className='hover:bg-muted/50 transition-colors'>
                    <TableCell>{v.venue_name}</TableCell>
                    <TableCell>{v.space_no}</TableCell>
                    <TableCell>{v.floor ?? '—'}</TableCell>
                    <TableCell>{v.capacity ?? '—'}</TableCell>
                    <TableCell>{v.equipment ?? '—'}</TableCell>
                    <TableCell>{v.hourly_rate ? `¥${v.hourly_rate}/小时` : '—'}</TableCell>
                    <TableCell><Badge variant={STATUS_VARIANT[v.status] ?? 'secondary'} className='capitalize'>{v.status}</Badge></TableCell>
                    <TableCell>{v.description ?? '—'}</TableCell>
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
