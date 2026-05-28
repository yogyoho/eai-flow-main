import { useState, type ReactNode } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Loader2, Plus, ShieldCheck } from 'lucide-react'
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { evaluationApi, type Evaluation } from '@/lib/api'
import { toast } from 'sonner'

const evalFormSchema = z.object({
  project_id: z.string().min(1, '请输入项目ID'),
  bid_id: z.string().min(1, '请输入投标ID'),
  evaluation_type: z.string().min(1, '请选择评审类型'),
  technical_score: z.string().optional(),
  commercial_score: z.string().optional(),
  evaluation_details: z.string().optional(),
})

type EvalFormValues = z.infer<typeof evalFormSchema>

interface EvaluationFormDialogProps {
  evaluation?: Evaluation
  onSuccess?: () => void
  children?: ReactNode
}

interface EvaluationVerifyDialogProps {
  evaluation: Evaluation
  onSuccess?: () => void
  children?: ReactNode
}

export function EvaluationFormDialog({ evaluation, onSuccess, children }: EvaluationFormDialogProps) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)

  const form = useForm<EvalFormValues>({
    resolver: zodResolver(evalFormSchema),
    defaultValues: {
      project_id: evaluation?.project_id ?? '',
      bid_id: evaluation?.bid_id ?? '',
      evaluation_type: evaluation?.evaluation_type ?? '',
      technical_score: evaluation?.technical_score?.toString() ?? '',
      commercial_score: evaluation?.commercial_score?.toString() ?? '',
      evaluation_details: evaluation?.evaluation_details ?? '',
    },
  })

  const onSubmit = async (values: EvalFormValues) => {
    setLoading(true)
    try {
      const data = {
        project_id: values.project_id,
        bid_id: values.bid_id,
        evaluation_type: values.evaluation_type,
        technical_score: values.technical_score ? parseFloat(values.technical_score) : undefined,
        commercial_score: values.commercial_score ? parseFloat(values.commercial_score) : undefined,
        evaluation_details: values.evaluation_details || undefined,
      }

      if (evaluation) {
        // Update not available in current API, so just show info
        toast.info('当前版本暂不支持修改评标记录')
      } else {
        await evaluationApi.create(data)
        toast.success('评标记录已创建')
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
        {children ?? (evaluation ? (
          <Button variant="outline" size="sm">编辑</Button>
        ) : (
          <Button size="sm">
            <Plus className="h-4 w-4 mr-1" />
            新增评分
          </Button>
        ))}
      </DialogTrigger>
      <DialogContent className="sm:max-w-[500px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{evaluation ? '编辑评标记录' : '新增评标评分'}</DialogTitle>
          <DialogDescription>
            {evaluation ? '修改评标评分信息' : '填写评标评分信息'}
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="project_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>项目 ID <span className="text-destructive">*</span></FormLabel>
                  <FormControl>
                    <Input placeholder="请输入项目ID" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="bid_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>投标 ID <span className="text-destructive">*</span></FormLabel>
                  <FormControl>
                    <Input placeholder="请输入投标ID" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="evaluation_type"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>评审类型 <span className="text-destructive">*</span></FormLabel>
                  <Select onValueChange={field.onChange} defaultValue={field.value}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="选择评审类型" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="技术评审">技术评审</SelectItem>
                      <SelectItem value="商务评审">商务评审</SelectItem>
                      <SelectItem value="综合评审">综合评审</SelectItem>
                      <SelectItem value="资格后审">资格后审</SelectItem>
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="grid grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="technical_score"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>技术得分</FormLabel>
                    <FormControl>
                      <Input type="number" step="0.01" min="0" max="100" placeholder="0-100" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="commercial_score"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>商务得分</FormLabel>
                    <FormControl>
                      <Input type="number" step="0.01" min="0" max="100" placeholder="0-100" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <FormField
              control={form.control}
              name="evaluation_details"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>评审详情</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="请输入评审详情..."
                      className="resize-none"
                      rows={4}
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
                {evaluation ? '保存修改' : '创建评分'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}


export function EvaluationVerifyDialog({ evaluation, onSuccess, children }: EvaluationVerifyDialogProps) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<{ passed: boolean; issues: unknown[] } | null>(null)

  const handleVerify = async () => {
    setLoading(true)
    setResult(null)
    try {
      const verifyResult = await evaluationApi.verify(evaluation.id)
      setResult(verifyResult)
      if (verifyResult.passed) {
        toast.success('核验通过')
      } else {
        toast.warning('核验未通过')
      }
      onSuccess?.()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '核验失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {children ?? (
          <Button variant="outline" size="sm">
            <ShieldCheck className="h-4 w-4 mr-1" />
            核验
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>评标核验</DialogTitle>
          <DialogDescription>
            对评标记录进行一致性核验
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="text-sm text-muted-foreground">
            <p>评审类型：{evaluation.evaluation_type}</p>
            <p>技术得分：{evaluation.technical_score?.toFixed(2) ?? '—'}</p>
            <p>商务得分：{evaluation.commercial_score?.toFixed(2) ?? '—'}</p>
            <p>综合得分：{evaluation.total_score?.toFixed(2) ?? '—'}</p>
          </div>

          {!result && (
            <Button onClick={handleVerify} disabled={loading} className="w-full">
              {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              开始核验
            </Button>
          )}

          {result && (
            <div className="space-y-4">
              <div className={`p-4 rounded-lg ${result.passed ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'}`}>
                <p className="font-medium">
                  {result.passed ? '核验通过' : '核验未通过'}
                </p>
                {result.issues && result.issues.length > 0 && (
                  <ul className="mt-2 text-sm list-disc list-inside">
                    {result.issues.map((issue, index) => (
                      <li key={index}>{String(issue)}</li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="flex gap-2">
                <Button variant="outline" onClick={handleVerify} disabled={loading} className="flex-1">
                  重新核验
                </Button>
                <Button onClick={() => setOpen(false)} className="flex-1">
                  完成
                </Button>
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
