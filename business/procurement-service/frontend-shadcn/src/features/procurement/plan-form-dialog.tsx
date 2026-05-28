import { useState, type ReactNode } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Loader2, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { planApi, type TenderPlan } from '@/lib/api'
import { toast } from 'sonner'

const planFormSchema = z.object({
  title: z.string().min(1, '请输入计划名称'),
  plan_no: z.string().min(1, '请输入计划编号'),
  procurement_type: z.string().min(1, '请选择采购类型'),
  procurement_method: z.string().optional(),
  dept_name: z.string().optional(),
  budget: z.string().optional(),
  estimated_price: z.string().optional(),
  funding_source: z.string().optional(),
  plan_year: z.string().optional(),
  estimated_start: z.string().optional(),
  estimated_end: z.string().optional(),
  description: z.string().optional(),
})

type PlanFormValues = z.infer<typeof planFormSchema>

interface PlanFormDialogProps {
  plan?: TenderPlan
  onSuccess?: () => void
  children?: ReactNode
}

export function PlanFormDialog({ plan, onSuccess, children }: PlanFormDialogProps) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)

  const form = useForm<PlanFormValues>({
    resolver: zodResolver(planFormSchema),
    defaultValues: {
      title: plan?.title ?? '',
      plan_no: plan?.plan_no ?? '',
      procurement_type: plan?.procurement_type ?? '',
      procurement_method: plan?.procurement_method ?? '',
      dept_name: plan?.dept_name ?? '',
      budget: plan?.budget?.toString() ?? '',
      estimated_price: plan?.estimated_price?.toString() ?? '',
      funding_source: plan?.funding_source ?? '',
      plan_year: plan?.plan_year?.toString() ?? '',
      estimated_start: plan?.estimated_start ?? '',
      estimated_end: plan?.estimated_end ?? '',
      description: plan?.description ?? '',
    },
  })

  const onSubmit = async (values: PlanFormValues) => {
    setLoading(true)
    try {
      const data = {
        title: values.title,
        plan_no: values.plan_no,
        procurement_type: values.procurement_type,
        procurement_method: values.procurement_method || undefined,
        dept_name: values.dept_name || undefined,
        budget: values.budget ? parseFloat(values.budget) : undefined,
        estimated_price: values.estimated_price ? parseFloat(values.estimated_price) : undefined,
        funding_source: values.funding_source || undefined,
        plan_year: values.plan_year ? parseInt(values.plan_year) : undefined,
        estimated_start: values.estimated_start || undefined,
        estimated_end: values.estimated_end || undefined,
        description: values.description || undefined,
      }

      if (plan) {
        await planApi.update(plan.id, data)
        toast.success('招标计划已更新')
      } else {
        await planApi.create(data)
        toast.success('招标计划已创建')
      }
      setOpen(false)
      form.reset()
      onSuccess?.()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '操作失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {children ?? (plan ? (
          <Button variant="outline" size="sm">编辑</Button>
        ) : (
          <Button size="sm">
            <Plus className="h-4 w-4 mr-1" />
            新建计划
          </Button>
        ))}
      </DialogTrigger>
      <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{plan ? '编辑招标计划' : '新建招标计划'}</DialogTitle>
          <DialogDescription>
            {plan ? '修改招标计划信息' : '填写招标计划详细信息'}
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="plan_no"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>计划编号</FormLabel>
                    <FormControl>
                      <Input placeholder="请输入计划编号" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="plan_year"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>计划年度</FormLabel>
                    <FormControl>
                      <Input placeholder="如：2026" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <FormField
              control={form.control}
              name="title"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>计划名称</FormLabel>
                  <FormControl>
                    <Input placeholder="请输入计划名称" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="grid grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="procurement_type"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>采购类型</FormLabel>
                    <Select onValueChange={field.onChange} defaultValue={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="选择采购类型" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="工程">工程</SelectItem>
                        <SelectItem value="货物">货物</SelectItem>
                        <SelectItem value="服务">服务</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="procurement_method"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>采购方式</FormLabel>
                    <Select onValueChange={field.onChange} defaultValue={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="选择采购方式" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="公开招标">公开招标</SelectItem>
                        <SelectItem value="邀请招标">邀请招标</SelectItem>
                        <SelectItem value="竞争性谈判">竞争性谈判</SelectItem>
                        <SelectItem value="单一来源">单一来源</SelectItem>
                        <SelectItem value="询价">询价</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="dept_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>需求部门</FormLabel>
                    <FormControl>
                      <Input placeholder="请输入部门名称" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="funding_source"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>资金来源</FormLabel>
                    <FormControl>
                      <Input placeholder="请输入资金来源" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="budget"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>预算金额(元)</FormLabel>
                    <FormControl>
                      <Input type="number" placeholder="请输入预算金额" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="estimated_price"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>估算价格(元)</FormLabel>
                    <FormControl>
                      <Input type="number" placeholder="请输入估算价格" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="estimated_start"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>预计开始日期</FormLabel>
                    <FormControl>
                      <Input type="date" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="estimated_end"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>预计结束日期</FormLabel>
                    <FormControl>
                      <Input type="date" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>备注说明</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="请输入备注说明..."
                      className="resize-none"
                      rows={3}
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                取消
              </Button>
              <Button type="submit" disabled={loading}>
                {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {plan ? '保存修改' : '创建计划'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
