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
import { expertApi, type Expert } from '@/lib/api'
import { toast } from 'sonner'

const expertFormSchema = z.object({
  name: z.string().min(1, '请输入专家姓名'),
  id_card: z.string().optional(),
  phone: z.string().optional(),
  email: z.string().optional(),
  expertise: z.string().min(1, '请输入专业领域'),
  title: z.string().optional(),
  organization: z.string().optional(),
  region: z.string().optional(),
  is_active: z.boolean().optional(),
  bank_account: z.string().optional(),
  bank_name: z.string().optional(),
  remark: z.string().optional(),
})

type ExpertFormValues = z.infer<typeof expertFormSchema>

interface ExpertFormDialogProps {
  expert?: Expert
  onSuccess?: () => void
  children?: ReactNode
}

export function ExpertFormDialog({ expert, onSuccess, children }: ExpertFormDialogProps) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)

  const form = useForm<ExpertFormValues>({
    resolver: zodResolver(expertFormSchema),
    defaultValues: {
      name: expert?.name ?? '',
      id_card: expert?.id_card ?? '',
      phone: expert?.phone ?? '',
      email: expert?.email ?? '',
      expertise: expert?.expertise ?? '',
      title: expert?.title ?? '',
      organization: expert?.organization ?? '',
      region: expert?.region ?? '',
      is_active: expert?.is_active ?? true,
      bank_account: expert?.bank_account ?? '',
      bank_name: expert?.bank_name ?? '',
      remark: expert?.remark ?? '',
    },
  })

  const onSubmit = async (values: ExpertFormValues) => {
    setLoading(true)
    try {
      const data = {
        name: values.name,
        id_card: values.id_card || undefined,
        phone: values.phone || undefined,
        email: values.email || undefined,
        expertise: values.expertise,
        title: values.title || undefined,
        organization: values.organization || undefined,
        region: values.region || undefined,
        is_active: values.is_active ?? true,
        bank_account: values.bank_account || undefined,
        bank_name: values.bank_name || undefined,
        remark: values.remark || undefined,
      }

      if (expert) {
        await expertApi.update(expert.id, data)
        toast.success('专家信息已更新')
      } else {
        await expertApi.create(data)
        toast.success('专家信息已创建')
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
        {children ?? (expert ? (
          <Button variant="outline" size="sm">编辑</Button>
        ) : (
          <Button size="sm">
            <Plus className="h-4 w-4 mr-1" />
            新增专家
          </Button>
        ))}
      </DialogTrigger>
      <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{expert ? '编辑专家' : '新增专家'}</DialogTitle>
          <DialogDescription>
            {expert ? '修改专家详细信息' : '填写专家详细信息'}
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>姓名 <span className="text-destructive">*</span></FormLabel>
                    <FormControl>
                      <Input placeholder="请输入专家姓名" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="id_card"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>身份证号</FormLabel>
                    <FormControl>
                      <Input placeholder="请输入身份证号" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="phone"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>联系电话</FormLabel>
                    <FormControl>
                      <Input placeholder="请输入联系电话" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="email"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>电子邮箱</FormLabel>
                    <FormControl>
                      <Input placeholder="请输入电子邮箱" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <FormField
              control={form.control}
              name="expertise"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>专业领域 <span className="text-destructive">*</span></FormLabel>
                  <Select onValueChange={field.onChange} defaultValue={field.value}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="选择专业领域" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="建筑工程">建筑工程</SelectItem>
                      <SelectItem value="市政工程">市政工程</SelectItem>
                      <SelectItem value="园林绿化">园林绿化</SelectItem>
                      <SelectItem value="机电设备">机电设备</SelectItem>
                      <SelectItem value="信息技术">信息技术</SelectItem>
                      <SelectItem value="医疗设备">医疗设备</SelectItem>
                      <SelectItem value="教学设备">教学设备</SelectItem>
                      <SelectItem value="其他">其他</SelectItem>
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="grid grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="title"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>职称</FormLabel>
                    <FormControl>
                      <Input placeholder="请输入职称" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="organization"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>工作单位</FormLabel>
                    <FormControl>
                      <Input placeholder="请输入工作单位" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="region"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>所在地区</FormLabel>
                    <FormControl>
                      <Input placeholder="请输入所在地区" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="bank_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>开户银行</FormLabel>
                    <FormControl>
                      <Input placeholder="请输入开户银行" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <FormField
              control={form.control}
              name="bank_account"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>银行账号</FormLabel>
                  <FormControl>
                    <Input placeholder="请输入银行账号" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="remark"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>备注</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="请输入备注信息..."
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
                {expert ? '保存修改' : '创建专家'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
