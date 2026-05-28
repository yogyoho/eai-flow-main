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
  CheckCircle2,
  Clock,
  Eye,
  ShieldCheck,
} from 'lucide-react'
import { evaluationApi, type Evaluation } from '@/lib/api'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { Search } from '@/components/search'
import { ThemeSwitch } from '@/components/theme-switch'
import { ConfigDrawer } from '@/components/config-drawer'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { EvaluationFormDialog, EvaluationVerifyDialog } from '@/features/procurement/evaluation-form-dialog'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import { Separator as SeparatorComponent } from '@/components/ui/separator'

export const Route = createFileRoute('/_authenticated/procurement/evaluations')({
  component: EvaluationsPage,
})

const STATUS_VARIANT: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  pending: 'default',
  in_progress: 'default',
  completed: 'default',
  verified: 'default',
  rejected: 'destructive',
}

function EvaluationsPage() {
  const [evals, setEvals] = useState<Evaluation[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [keyword, setKeyword] = useState('')
  const [detailEval, setDetailEval] = useState<Evaluation | null>(null)
  const [detailSheetOpen, setDetailSheetOpen] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await evaluationApi.list({ limit: String(100) })
      setEvals(data.evaluations)
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const formatDate = (date?: string) =>
    date ? new Date(date).toLocaleDateString('zh-CN') : '—'

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
            <h2 className='text-2xl font-bold tracking-tight'>评标管理</h2>
            <p className='text-muted-foreground'>管理评标记录和评审结果</p>
          </div>
          <div className='flex items-center gap-2'>
            <div className='relative'>
              <SearchIcon className='absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground' />
              <Input
                placeholder='搜索...'
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                className='pl-9 w-48'
              />
            </div>
            <Button variant='outline' size='icon' onClick={load} disabled={loading}>
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            </Button>
            <EvaluationFormDialog onSuccess={load} />
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
        ) : evals.length === 0 ? (
          <div className='flex flex-col items-center justify-center py-16 text-muted-foreground'>
            <FileX className='h-12 w-12 mb-4 opacity-20' />
            <p className='text-sm'>暂无评标记录</p>
          </div>
        ) : (
          <div className='rounded-lg border overflow-hidden'>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>评审类型</TableHead>
                  <TableHead>技术得分</TableHead>
                  <TableHead>商务得分</TableHead>
                  <TableHead>总分</TableHead>
                  <TableHead>排名</TableHead>
                  <TableHead>核验</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>完成时间</TableHead>
                  <TableHead className="w-[120px]">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {evals.map((e) => (
                  <TableRow key={e.id} className='hover:bg-muted/50 transition-colors'>
                    <TableCell>{e.evaluation_type}</TableCell>
                    <TableCell>{e.technical_score?.toFixed(2) ?? '—'}</TableCell>
                    <TableCell>{e.commercial_score?.toFixed(2) ?? '—'}</TableCell>
                    <TableCell className="font-medium">{e.total_score?.toFixed(2) ?? '—'}</TableCell>
                    <TableCell>{e.ranking ? `#${e.ranking}` : '—'}</TableCell>
                    <TableCell>
                      {e.verified
                        ? <CheckCircle2 className='h-4 w-4 text-green-600' />
                        : <Clock className='h-4 w-4 text-muted-foreground' />
                      }
                    </TableCell>
                    <TableCell><Badge variant={STATUS_VARIANT[e.status] ?? 'secondary'} className='capitalize'>{e.status}</Badge></TableCell>
                    <TableCell>{formatDate(e.completed_at ?? e.created_at)}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          onClick={() => { setDetailEval(e); setDetailSheetOpen(true) }}
                        >
                          <Eye className="h-4 w-4" />
                        </Button>
                        {!e.verified && e.status !== 'completed' && (
                          <EvaluationVerifyDialog evaluation={e} onSuccess={load}>
                            <Button variant="ghost" size="icon" className="h-8 w-8">
                              <ShieldCheck className="h-4 w-4" />
                            </Button>
                          </EvaluationVerifyDialog>
                        )}
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
            <SheetTitle>评标详情</SheetTitle>
            <SheetDescription>
              {detailEval ? `评审类型：${detailEval.evaluation_type}` : '加载中...'}
            </SheetDescription>
          </SheetHeader>

          {detailEval && (
            <div className="mt-6 space-y-6">
              <div className="space-y-4">
                <div>
                  <h3 className="text-lg font-semibold">评标记录详情</h3>
                  <div className="flex items-center gap-2 mt-2 flex-wrap">
                    <Badge variant={STATUS_VARIANT[detailEval.status] ?? 'secondary'}>
                      {detailEval.status}
                    </Badge>
                    <Badge variant="outline">{detailEval.evaluation_type}</Badge>
                    {detailEval.verified && (
                      <Badge variant="default" className="bg-green-600">
                        <CheckCircle2 className="h-3 w-3 mr-1" />
                        已核验
                      </Badge>
                    )}
                  </div>
                </div>

                <SeparatorComponent />

                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="text-muted-foreground">技术得分</p>
                    <p className="font-medium text-lg">{detailEval.technical_score?.toFixed(2) ?? '—'}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">商务得分</p>
                    <p className="font-medium text-lg">{detailEval.commercial_score?.toFixed(2) ?? '—'}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">综合得分</p>
                    <p className="font-medium text-lg text-primary">{detailEval.total_score?.toFixed(2) ?? '—'}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">排名</p>
                    <p className="font-medium text-lg">{detailEval.ranking ? `#${detailEval.ranking}` : '—'}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">评审类型</p>
                    <p className="font-medium">{detailEval.evaluation_type}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">完成时间</p>
                    <p className="font-medium">{formatDate(detailEval.completed_at)}</p>
                  </div>
                </div>

                {detailEval.evaluation_details && (
                  <>
                    <SeparatorComponent />
                    <div>
                      <p className="text-muted-foreground mb-1">评审详情</p>
                      <p className="text-sm whitespace-pre-wrap">{detailEval.evaluation_details}</p>
                    </div>
                  </>
                )}

                {detailEval.verification_comment && (
                  <>
                    <SeparatorComponent />
                    <div>
                      <p className="text-muted-foreground mb-1">核验意见</p>
                      <p className="text-sm">{detailEval.verification_comment}</p>
                    </div>
                  </>
                )}

                <SeparatorComponent />

                <div className="text-xs text-muted-foreground space-y-1">
                  <p>创建时间：{formatDate(detailEval.created_at)}</p>
                  <p>更新时间：{formatDate(detailEval.updated_at)}</p>
                </div>
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </>
  )
}
