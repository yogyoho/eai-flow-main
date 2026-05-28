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
  Upload,
  Eye,
  Pencil,
} from 'lucide-react'
import { expertApi, type Expert } from '@/lib/api'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { Search } from '@/components/search'
import { ThemeSwitch } from '@/components/theme-switch'
import { ConfigDrawer } from '@/components/config-drawer'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ExpertFormDialog } from '@/features/procurement/expert-form-dialog'
import { ExpertDrawDialog } from '@/features/procurement/expert-draw-dialog'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import { Separator as SeparatorComponent } from '@/components/ui/separator'

export const Route = createFileRoute('/_authenticated/procurement/experts')({
  component: ExpertsPage,
})

function ExpertsPage() {
  const [experts, setExperts] = useState<Expert[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [keyword, setKeyword] = useState('')
  const [detailExpert, setDetailExpert] = useState<Expert | null>(null)
  const [detailSheetOpen, setDetailSheetOpen] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params: Record<string, string> = {}
      if (keyword) params.keyword = keyword
      params.limit = '100'
      const data = await expertApi.list(params)
      setExperts(data.experts)
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [keyword])

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
            <h2 className='text-2xl font-bold tracking-tight'>评标专家管理</h2>
            <p className='text-muted-foreground'>管理评标专家库</p>
          </div>
          <div className='flex items-center gap-2'>
            <div className='relative'>
              <SearchIcon className='absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground' />
              <Input
                placeholder='搜索专家姓名...'
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                className='pl-9 w-48'
              />
            </div>
            <Button variant='outline' size='icon' onClick={load} disabled={loading}>
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            </Button>
            <Button size='sm' variant='outline'>
              <Upload className='h-4 w-4 mr-1' />
              批量导入
            </Button>
            <ExpertFormDialog onSuccess={load} />
            <ExpertDrawDialog onSuccess={load} />
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
        ) : experts.length === 0 ? (
          <div className='flex flex-col items-center justify-center py-16 text-muted-foreground'>
            <FileX className='h-12 w-12 mb-4 opacity-20' />
            <p className='text-sm'>暂无专家数据</p>
          </div>
        ) : (
          <div className='rounded-lg border overflow-hidden'>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>姓名</TableHead>
                  <TableHead>专业领域</TableHead>
                  <TableHead>地区</TableHead>
                  <TableHead>职称</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>评标次数</TableHead>
                  <TableHead>平均分</TableHead>
                  <TableHead>联系电话</TableHead>
                  <TableHead className="w-[100px]">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {experts.map((e) => (
                  <TableRow key={e.id} className='hover:bg-muted/50 transition-colors'>
                    <TableCell>{e.name}</TableCell>
                    <TableCell>{e.expertise}</TableCell>
                    <TableCell>{e.region ?? '—'}</TableCell>
                    <TableCell>{e.title ?? '—'}</TableCell>
                    <TableCell>
                      <Badge variant={e.is_active ? 'default' : 'secondary'} className='capitalize'>
                        {e.is_active ? '正常' : '停用'}
                      </Badge>
                    </TableCell>
                    <TableCell>{e.evaluation_count}</TableCell>
                    <TableCell>{e.avg_score ? e.avg_score.toFixed(2) : '—'}</TableCell>
                    <TableCell>{e.phone ?? '—'}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          onClick={() => { setDetailExpert(e); setDetailSheetOpen(true) }}
                        >
                          <Eye className="h-4 w-4" />
                        </Button>
                        <ExpertFormDialog expert={e} onSuccess={load}>
                          <Button variant="ghost" size="icon" className="h-8 w-8">
                            <Pencil className="h-4 w-4" />
                          </Button>
                        </ExpertFormDialog>
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
            <SheetTitle>专家详情</SheetTitle>
            <SheetDescription>
              {detailExpert ? `姓名：${detailExpert.name}` : '加载中...'}
            </SheetDescription>
          </SheetHeader>

          {detailExpert && (
            <div className="mt-6 space-y-6">
              <div className="space-y-4">
                <div>
                  <h3 className="text-lg font-semibold">{detailExpert.name}</h3>
                  <div className="flex items-center gap-2 mt-2 flex-wrap">
                    <Badge variant={detailExpert.is_active ? 'default' : 'secondary'}>
                      {detailExpert.is_active ? '正常' : '停用'}
                    </Badge>
                    <Badge variant="outline">{detailExpert.expertise}</Badge>
                  </div>
                </div>

                <SeparatorComponent />

                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="text-muted-foreground">职称</p>
                    <p className="font-medium">{detailExpert.title ?? '—'}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">工作单位</p>
                    <p className="font-medium">{detailExpert.organization ?? '—'}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">联系电话</p>
                    <p className="font-medium">{detailExpert.phone ?? '—'}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">电子邮箱</p>
                    <p className="font-medium">{detailExpert.email ?? '—'}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">所在地区</p>
                    <p className="font-medium">{detailExpert.region ?? '—'}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">评标次数</p>
                    <p className="font-medium">{detailExpert.evaluation_count} 次</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">平均评分</p>
                    <p className="font-medium">{detailExpert.avg_score ? detailExpert.avg_score.toFixed(2) : '—'}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">身份证号</p>
                    <p className="font-medium">{detailExpert.id_card ?? '—'}</p>
                  </div>
                </div>

                {(detailExpert.bank_name || detailExpert.bank_account) && (
                  <>
                    <SeparatorComponent />
                    <div>
                      <p className="text-muted-foreground mb-2">收款信息</p>
                      <div className="grid grid-cols-2 gap-4 text-sm">
                        <div>
                          <p className="text-muted-foreground">开户银行</p>
                          <p className="font-medium">{detailExpert.bank_name ?? '—'}</p>
                        </div>
                        <div>
                          <p className="text-muted-foreground">银行账号</p>
                          <p className="font-medium">{detailExpert.bank_account ?? '—'}</p>
                        </div>
                      </div>
                    </div>
                  </>
                )}

                {detailExpert.remark && (
                  <>
                    <SeparatorComponent />
                    <div>
                      <p className="text-muted-foreground mb-1">备注</p>
                      <p className="text-sm whitespace-pre-wrap">{detailExpert.remark}</p>
                    </div>
                  </>
                )}

                <SeparatorComponent />

                <div className="text-xs text-muted-foreground space-y-1">
                  <p>创建时间：{formatDate(detailExpert.created_at)}</p>
                  <p>更新时间：{formatDate(detailExpert.updated_at)}</p>
                </div>
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </>
  )
}
