import { useState, useEffect } from 'react'
import { Eye } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter,
} from '@/components/ui/sheet'
import { Separator } from '@/components/ui/separator'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card'
import { planApi, type TenderPlan } from '@/lib/api'

interface PlanDetailSheetProps {
  planId: string | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function PlanDetailSheet({ planId, open, onOpenChange }: PlanDetailSheetProps) {
  const [plan, setPlan] = useState<TenderPlan | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (planId && open) {
      setLoading(true)
      planApi.get(planId)
        .then(setPlan)
        .catch(console.error)
        .finally(() => setLoading(false))
    }
  }, [planId, open])

  const formatDate = (date?: string) =>
    date ? new Date(date).toLocaleDateString('zh-CN') : '—'
  const formatMoney = (amount?: number) =>
    amount ? `¥${Number(amount).toLocaleString('zh-CN')}` : '—'

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="sm:max-w-[540px]">
        <SheetHeader className="pt-6 pb-4">
          <SheetTitle>招标计划详情</SheetTitle>
          <SheetDescription>
            {plan ? `计划编号：${plan.plan_no}` : '加载中...'}
          </SheetDescription>
        </SheetHeader>

        <div className="pb-6 flex-1 overflow-y-auto">
          {loading ? (
            <div className="space-y-4">
              <Skeleton className="h-8 w-1/3" />
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-32 w-full" />
            </div>
          ) : plan ? (
            <div className="space-y-6">
              {/* 基本信息卡片 */}
              <Card className="p-5">
                <CardHeader className="p-0 pb-4">
                  <div className="space-y-3">
                    <CardTitle className="text-xl leading-relaxed">
                      {plan.title}
                    </CardTitle>
                    <CardDescription className="flex items-center gap-2 flex-wrap">
                      <Badge variant="outline" className="font-normal">
                        {plan.procurement_type}
                      </Badge>
                      {plan.procurement_method && (
                        <Badge variant="secondary" className="font-normal">
                          {plan.procurement_method}
                        </Badge>
                      )}
                      <Badge>{plan.status}</Badge>
                    </CardDescription>
                  </div>
                </CardHeader>
              </Card>

              {/* 详细信息卡片 */}
              <Card className="p-5">
                <CardContent className="p-0">
                  <div className="grid grid-cols-2 gap-x-8 gap-y-5">
                    <div className="space-y-1">
                      <p className="text-sm text-muted-foreground">计划年度</p>
                      <p className="text-sm font-medium">{plan.plan_year ?? '—'}</p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-sm text-muted-foreground">需求部门</p>
                      <p className="text-sm font-medium">{plan.dept_name ?? '—'}</p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-sm text-muted-foreground">预算金额</p>
                      <p className="text-sm font-medium">{formatMoney(plan.budget)}</p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-sm text-muted-foreground">估算价格</p>
                      <p className="text-sm font-medium">{formatMoney(plan.estimated_price)}</p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-sm text-muted-foreground">资金来源</p>
                      <p className="text-sm font-medium">{plan.funding_source ?? '—'}</p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-sm text-muted-foreground">预计开始</p>
                      <p className="text-sm font-medium">{formatDate(plan.estimated_start)}</p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-sm text-muted-foreground">预计结束</p>
                      <p className="text-sm font-medium">{formatDate(plan.estimated_end)}</p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-sm text-muted-foreground">创建人</p>
                      <p className="text-sm font-medium">{plan.created_by ?? '—'}</p>
                    </div>
                  </div>

                  {plan.description && (
                    <>
                      <Separator className="my-5" />
                      <div className="space-y-2">
                        <p className="text-sm text-muted-foreground">备注说明</p>
                        <p className="text-sm leading-relaxed whitespace-pre-wrap">
                          {plan.description}
                        </p>
                      </div>
                    </>
                  )}

                  <Separator className="my-5" />

                  <div className="space-y-1">
                    <p className="text-xs text-muted-foreground">
                      创建时间：{formatDate(plan.created_at)}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      更新时间：{formatDate(plan.updated_at)}
                    </p>
                  </div>
                </CardContent>
              </Card>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
              <p>未找到计划详情</p>
            </div>
          )}
        </div>

        <SheetFooter className="py-4 border-t bg-muted/30">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            关闭
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}

interface PlanDetailButtonProps {
  plan: TenderPlan
  onOpenChange: (open: boolean) => void
}

export function PlanDetailButton({ plan: _plan, onOpenChange }: PlanDetailButtonProps) {
  return (
    <Button
      variant="ghost"
      size="icon"
      className="h-8 w-8"
      onClick={() => onOpenChange(true)}
    >
      <Eye className="h-4 w-4" />
    </Button>
  )
}
