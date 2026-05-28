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
import { projectApi, type TenderProject } from '@/lib/api'
import { toast } from 'sonner'

const projectFormSchema = z.object({
  title: z.string().min(1, '请输入项目名称'),
  project_no: z.string().min(1, '请输入项目编号'),
  procurement_type: z.string().min(1, '请选择采购类型'),
  procurement_method: z.string().min(1, '请选择采购方式'),
  dept_name: z.string().optional(),
  budget: z.string().optional(),
  control_price: z.string().optional(),
  funding_source: z.string().optional(),
  qualification_requirements: z.string().optional(),
  description: z.string().optional(),
  announcement_url: z.string().optional(),
})

type ProjectFormValues = z.infer<typeof projectFormSchema>

interface ProjectFormDialogProps {
  project?: TenderProject
  onSuccess?: () => void
  children?: ReactNode
}

export function ProjectFormDialog({ project, onSuccess, children }: ProjectFormDialogProps) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)

  const form = useForm<ProjectFormValues>({
    resolver: zodResolver(projectFormSchema),
    defaultValues: {
      title: project?.title ?? '',
      project_no: project?.project_no ?? '',
      procurement_type: project?.procurement_type ?? '',
      procurement_method: project?.procurement_method ?? '',
      dept_name: project?.dept_name ?? '',
      budget: project?.budget?.toString() ?? '',
      control_price: project?.control_price?.toString() ?? '',
      funding_source: project?.funding_source ?? '',
      qualification_requirements: project?.qualification_requirements ?? '',
      description: project?.description ?? '',
      announcement_url: project?.announcement_url ?? '',
    },
  })

  const onSubmit = async (values: ProjectFormValues) => {
    setLoading(true)
    try {
      const data = {
        title: values.title,
        project_no: values.project_no,
        procurement_type: values.procurement_type,
        procurement_method: values.procurement_method,
        dept_name: values.dept_name || undefined,
        budget: values.budget ? parseFloat(values.budget) : undefined,
        control_price: values.control_price ? parseFloat(values.control_price) : undefined,
        funding_source: values.funding_source || undefined,
        qualification_requirements: values.qualification_requirements || undefined,
        description: values.description || undefined,
        announcement_url: values.announcement_url || undefined,
      }

      if (project) {
        await projectApi.update(project.id, data)
        toast.success('招标项目已更新')
      } else {
        await projectApi.create(data)
        toast.success('招标项目已创建')
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
        {children ?? (project ? (
          <Button variant="outline" size="sm">编辑</Button>
        ) : (
          <Button size="sm">
            <Plus className="h-4 w-4 mr-1" />
            新建项目
          </Button>
        ))}
      </DialogTrigger>
      <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{project ? '编辑招标项目' : '新建招标项目'}</DialogTitle>
          <DialogDescription>
            {project ? '修改招标项目信息' : '填写招标项目详细信息'}
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="project_no"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>项目编号</FormLabel>
                    <FormControl>
                      <Input placeholder="请输入项目编号" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
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
            </div>

            <FormField
              control={form.control}
              name="title"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>项目名称</FormLabel>
                  <FormControl>
                    <Input placeholder="请输入项目名称" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="grid grid-cols-2 gap-4">
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
              <FormField
                control={form.control}
                name="dept_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>采购部门</FormLabel>
                    <FormControl>
                      <Input placeholder="请输入部门名称" {...field} />
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
                name="control_price"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>控制价(元)</FormLabel>
                    <FormControl>
                      <Input type="number" placeholder="请输入控制价" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

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

            <FormField
              control={form.control}
              name="qualification_requirements"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>资质要求</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="请输入投标人资质要求..."
                      className="resize-none"
                      rows={2}
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>项目描述</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="请输入项目描述..."
                      className="resize-none"
                      rows={3}
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="announcement_url"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>公告链接</FormLabel>
                  <FormControl>
                    <Input placeholder="请输入公告链接" {...field} />
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
                {project ? '保存修改' : '创建项目'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
