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
import { bidderApi, type Bidder } from '@/lib/api'
import { toast } from 'sonner'

const bidderFormSchema = z.object({
  name: z.string().min(1, '请输入企业名称'),
  unified_credit_code: z.string().optional(),
  legal_person: z.string().optional(),
  contact_person: z.string().optional(),
  phone: z.string().optional(),
  email: z.string().optional(),
  address: z.string().optional(),
  region: z.string().optional(),
  business_scope: z.string().optional(),
  credit_rating: z.string().optional(),
  status: z.string().min(1, '请选择状态'),
  registration_date: z.string().optional(),
  remark: z.string().optional(),
})

type BidderFormValues = z.infer<typeof bidderFormSchema>

interface BidderFormDialogProps {
  bidder?: Bidder
  onSuccess?: () => void
  children?: ReactNode
}

export function BidderFormDialog({ bidder, onSuccess, children }: BidderFormDialogProps) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)

  const form = useForm<BidderFormValues>({
    resolver: zodResolver(bidderFormSchema),
    defaultValues: {
      name: bidder?.name ?? '',
      unified_credit_code: bidder?.unified_credit_code ?? '',
      legal_person: bidder?.legal_person ?? '',
      contact_person: bidder?.contact_person ?? '',
      phone: bidder?.phone ?? '',
      email: bidder?.email ?? '',
      address: bidder?.address ?? '',
      region: bidder?.region ?? '',
      business_scope: bidder?.business_scope ?? '',
      credit_rating: bidder?.credit_rating ?? '',
      status: bidder?.status ?? 'active',
      registration_date: bidder?.registration_date ?? '',
      remark: bidder?.remark ?? '',
    },
  })

  const onSubmit = async (values: BidderFormValues) => {
    setLoading(true)
    try {
      const data = {
        name: values.name,
        unified_credit_code: values.unified_credit_code || undefined,
        legal_person: values.legal_person || undefined,
        contact_person: values.contact_person || undefined,
        phone: values.phone || undefined,
        email: values.email || undefined,
        address: values.address || undefined,
        region: values.region || undefined,
        business_scope: values.business_scope || undefined,
        credit_rating: values.credit_rating || undefined,
        status: values.status,
        registration_date: values.registration_date || undefined,
        remark: values.remark || undefined,
      }

      if (bidder) {
        await bidderApi.update(bidder.id, data)
        toast.success('投标人信息已更新')
      } else {
        await bidderApi.create(data)
        toast.success('投标人信息已创建')
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
        {children ?? (bidder ? (
          <Button variant="outline" size="sm">编辑</Button>
        ) : (
          <Button size="sm">
            <Plus className="h-4 w-4 mr-1" />
            新增投标人
          </Button>
        ))}
      </DialogTrigger>
      <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{bidder ? '编辑投标人' : '新增投标人'}</DialogTitle>
          <DialogDescription>
            {bidder ? '修改投标人详细信息' : '填写投标人详细信息'}
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>企业名称 <span className="text-destructive">*</span></FormLabel>
                  <FormControl>
                    <Input placeholder="请输入企业名称" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="grid grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="unified_credit_code"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>统一信用代码</FormLabel>
                    <FormControl>
                      <Input placeholder="请输入统一信用代码" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="legal_person"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>法人代表</FormLabel>
                    <FormControl>
                      <Input placeholder="请输入法人代表" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="contact_person"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>联系人</FormLabel>
                    <FormControl>
                      <Input placeholder="请输入联系人" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
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
            </div>

            <div className="grid grid-cols-2 gap-4">
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
            </div>

            <FormField
              control={form.control}
              name="address"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>详细地址</FormLabel>
                  <FormControl>
                    <Input placeholder="请输入详细地址" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="grid grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="business_scope"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>经营范围</FormLabel>
                    <FormControl>
                      <Input placeholder="请输入经营范围" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="credit_rating"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>信用评级</FormLabel>
                    <Select onValueChange={field.onChange} defaultValue={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="选择信用评级" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="AAA">AAA</SelectItem>
                        <SelectItem value="AA">AA</SelectItem>
                        <SelectItem value="A">A</SelectItem>
                        <SelectItem value="BBB">BBB</SelectItem>
                        <SelectItem value="BB">BB</SelectItem>
                        <SelectItem value="B">B</SelectItem>
                        <SelectItem value="CCC">CCC</SelectItem>
                        <SelectItem value="CC">CC</SelectItem>
                        <SelectItem value="C">C</SelectItem>
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
                name="status"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>状态 <span className="text-destructive">*</span></FormLabel>
                    <Select onValueChange={field.onChange} defaultValue={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="选择状态" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="active">正常</SelectItem>
                        <SelectItem value="inactive">停用</SelectItem>
                        <SelectItem value="pending">待审核</SelectItem>
                        <SelectItem value="suspended">暂停</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="registration_date"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>注册日期</FormLabel>
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
                {bidder ? '保存修改' : '创建投标人'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
