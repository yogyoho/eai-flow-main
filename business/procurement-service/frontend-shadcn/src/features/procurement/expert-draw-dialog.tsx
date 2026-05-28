import { useState, type ReactNode } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Loader2, Shuffle, CheckCircle2 } from 'lucide-react'
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
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { expertApi } from '@/lib/api'
import { toast } from 'sonner'

const drawFormSchema = z.object({
  project_id: z.string().min(1, '请输入项目ID'),
  required_count: z.string().min(1, '请输入抽取人数'),
  draw_method: z.string().optional(),
})

type DrawFormValues = z.infer<typeof drawFormSchema>

interface ExpertDrawDialogProps {
  onSuccess?: () => void
  children?: ReactNode
}

export function ExpertDrawDialog({ onSuccess, children }: ExpertDrawDialogProps) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<unknown>(null)

  const form = useForm<DrawFormValues>({
    resolver: zodResolver(drawFormSchema),
    defaultValues: {
      project_id: '',
      required_count: '5',
      draw_method: 'random',
    },
  })

  const handleDraw = async (values: DrawFormValues) => {
    setLoading(true)
    setResult(null)
    try {
      const data = {
        project_id: values.project_id,
        required_count: parseInt(values.required_count),
        draw_method: values.draw_method,
      }
      const drawResult = await expertApi.draw(data)
      setResult(drawResult)
      toast.success('专家抽取完成')
      onSuccess?.()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '专家抽取失败')
    } finally {
      setLoading(false)
    }
  }

  const resetForm = () => {
    setResult(null)
    form.reset()
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {children ?? (
          <Button size="sm">
            <Shuffle className="h-4 w-4 mr-1" />
            抽取专家
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>专家抽取</DialogTitle>
          <DialogDescription>
            根据项目需求抽取符合条件的评标专家
          </DialogDescription>
        </DialogHeader>

        {!result ? (
          <Form {...form}>
            <form onSubmit={form.handleSubmit(handleDraw)} className="space-y-4">
              <FormField
                control={form.control}
                name="project_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>招标项目 ID <span className="text-destructive">*</span></FormLabel>
                    <FormControl>
                      <Input placeholder="请输入招标项目ID" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="required_count"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>抽取人数 <span className="text-destructive">*</span></FormLabel>
                    <FormControl>
                      <Input type="number" min="1" max="20" placeholder="请输入抽取人数" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="draw_method"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>抽取方式</FormLabel>
                    <Select onValueChange={field.onChange} defaultValue={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="选择抽取方式" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="random">随机抽取</SelectItem>
                        <SelectItem value="weighted">加权随机</SelectItem>
                        <SelectItem value="balanced">均衡抽取</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <Alert>
                <AlertTitle>抽取规则</AlertTitle>
                <AlertDescription>
                  <ul className="text-sm mt-2 space-y-1 list-disc list-inside text-muted-foreground">
                    <li>系统将自动过滤与本项目有利益关系的专家</li>
                    <li>优先抽取评标经验丰富且评分较高的专家</li>
                    <li>同一专家被连续抽取次数不超过3次</li>
                  </ul>
                </AlertDescription>
              </Alert>

              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                  取消
                </Button>
                <Button type="submit" disabled={loading}>
                  {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  开始抽取
                </Button>
              </DialogFooter>
            </form>
          </Form>
        ) : (
          <div className="space-y-4">
            <Alert>
              <CheckCircle2 className="h-4 w-4" />
              <AlertTitle>抽取成功</AlertTitle>
              <AlertDescription>
                已成功抽取专家，请确认是否满意抽取结果
              </AlertDescription>
            </Alert>

            <div className="text-sm text-muted-foreground">
              <pre className="whitespace-pre-wrap bg-muted p-4 rounded-lg overflow-auto max-h-[300px]">
                {JSON.stringify(result, null, 2)}
              </pre>
            </div>

            <div className="flex gap-2">
              <Button variant="outline" onClick={resetForm} className="flex-1">
                <Shuffle className="h-4 w-4 mr-1" />
                重新抽取
              </Button>
              <Button onClick={() => setOpen(false)} className="flex-1">
                确认抽取
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
