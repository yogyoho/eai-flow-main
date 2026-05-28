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
import { bidApi, type Bid } from '@/lib/api'
import { toast } from 'sonner'

const bidFormSchema = z.object({
  project_id: z.string().min(1, '请选择招标项目'),
  bidder_id: z.string().min(1, '请选择投标人'),
  bid_no: z.string().min(1, '请输入投标编号'),
  bid_price: z.string().optional(),
  technical_proposal_url: z.string().optional(),
})

type BidFormValues = z.infer<typeof bidFormSchema>

interface BidFormDialogProps {
  bid?: Bid
  onSuccess?: () => void
  children?: ReactNode
}

export function BidFormDialog({ bid, onSuccess, children }: BidFormDialogProps) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)

  const form = useForm<BidFormValues>({
    resolver: zodResolver(bidFormSchema),
    defaultValues: {
      project_id: bid?.project_id ?? '',
      bidder_id: bid?.bidder_id ?? '',
      bid_no: bid?.bid_no ?? '',
      bid_price: bid?.bid_price?.toString() ?? '',
      technical_proposal_url: bid?.technical_proposal_url ?? '',
    },
  })

  const onSubmit = async (values: BidFormValues) => {
    setLoading(true)
    try {
      const data = {
        project_id: values.project_id,
        bidder_id: values.bidder_id,
        bid_no: values.bid_no,
        bid_price: values.bid_price ? parseFloat(values.bid_price) : undefined,
        technical_proposal_url: values.technical_proposal_url || undefined,
      }

      if (bid) {
        await bidApi.update(bid.id, data)
        toast.success('投标记录已更新')
      } else {
        await bidApi.create(data)
        toast.success('投标记录已创建')
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
        {children ?? (bid ? (
          <Button variant="outline" size="sm">编辑</Button>
        ) : (
          <Button size="sm">
            <Plus className="h-4 w-4 mr-1" />
            提交投标
          </Button>
        ))}
      </DialogTrigger>
      <DialogContent className="sm:max-w-[500px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{bid ? '编辑投标记录' : '提交投标'}</DialogTitle>
          <DialogDescription>
            {bid ? '修改投标记录信息' : '填写投标信息并提交'}
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="bid_no"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>投标编号 <span className="text-destructive">*</span></FormLabel>
                  <FormControl>
                    <Input placeholder="请输入投标编号" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

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
              name="bidder_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>投标人 ID <span className="text-destructive">*</span></FormLabel>
                  <FormControl>
                    <Input placeholder="请输入投标人ID" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="bid_price"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>投标报价(元)</FormLabel>
                  <FormControl>
                    <Input type="number" placeholder="请输入投标报价" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="technical_proposal_url"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>技术方案链接</FormLabel>
                  <FormControl>
                    <Input placeholder="请输入技术方案链接" {...field} />
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
                {bid ? '保存修改' : '提交投标'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
