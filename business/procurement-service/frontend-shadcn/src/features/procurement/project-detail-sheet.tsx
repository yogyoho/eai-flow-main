import { useState, useEffect } from 'react'
import { Eye, Loader2, ExternalLink, Send } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import { Separator } from '@/components/ui/separator'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { projectApi, type TenderProject } from '@/lib/api'
import { toast } from 'sonner'

interface ProjectDetailSheetProps {
  projectId: string | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onRefresh?: () => void
}

export function ProjectDetailSheet({ projectId, open, onOpenChange, onRefresh }: ProjectDetailSheetProps) {
  const [project, setProject] = useState<TenderProject | null>(null)
  const [loading, setLoading] = useState(false)
  const [publishing, setPublishing] = useState(false)

  useEffect(() => {
    if (projectId && open) {
      setLoading(true)
      projectApi.get(projectId)
        .then(setProject)
        .catch(console.error)
        .finally(() => setLoading(false))
    } else {
      setProject(null)
    }
  }, [projectId, open])

  const handlePublish = async () => {
    if (!project) return
    setPublishing(true)
    try {
      await projectApi.publish(project.id)
      toast.success('项目已发布')
      onRefresh?.()
      setProject({ ...project, status: 'published' })
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '发布失败')
    } finally {
      setPublishing(false)
    }
  }

  const formatDate = (date?: string) =>
    date ? new Date(date).toLocaleDateString('zh-CN') : '—'
  const formatMoney = (amount?: number) =>
    amount ? `¥${Number(amount).toLocaleString('zh-CN')}` : '—'

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="sm:max-w-[500px] overflow-y-auto">
        <SheetHeader>
          <SheetTitle>招标项目详情</SheetTitle>
          <SheetDescription>
            {project ? `项目编号：${project.project_no}` : '加载中...'}
          </SheetDescription>
        </SheetHeader>

        {loading ? (
          <div className="mt-6 space-y-4">
            <Skeleton className="h-8 w-1/3" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-32 w-full" />
          </div>
        ) : project ? (
          <div className="mt-6 space-y-6">
            <div className="space-y-4">
              <div>
                <h3 className="text-lg font-semibold">{project.title}</h3>
                <div className="flex items-center gap-2 mt-2 flex-wrap">
                  <Badge variant="outline">{project.procurement_type}</Badge>
                  <Badge variant="secondary">{project.procurement_method}</Badge>
                  <Badge>{project.status}</Badge>
                </div>
              </div>

              {project.announcement_url && (
                <a
                  href={project.announcement_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 text-sm text-blue-600 hover:underline"
                >
                  <ExternalLink className="h-4 w-4" />
                  查看招标公告
                </a>
              )}

              <Separator />

              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-muted-foreground">采购部门</p>
                  <p className="font-medium">{project.dept_name ?? '—'}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">资金来源</p>
                  <p className="font-medium">{project.funding_source ?? '—'}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">预算金额</p>
                  <p className="font-medium">{formatMoney(project.budget)}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">控制价</p>
                  <p className="font-medium">{formatMoney(project.control_price)}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">投标开始</p>
                  <p className="font-medium">{formatDate(project.bidding_start)}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">投标截止</p>
                  <p className="font-medium">{formatDate(project.bidding_end)}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">评标日期</p>
                  <p className="font-medium">{formatDate(project.evaluation_date)}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">发布人</p>
                  <p className="font-medium">{project.created_by ?? '—'}</p>
                </div>
              </div>

              {project.qualification_requirements && (
                <>
                  <Separator />
                  <div>
                    <p className="text-muted-foreground mb-1">资质要求</p>
                    <p className="text-sm whitespace-pre-wrap">{project.qualification_requirements}</p>
                  </div>
                </>
              )}

              {project.description && (
                <>
                  <Separator />
                  <div>
                    <p className="text-muted-foreground mb-1">项目描述</p>
                    <p className="text-sm whitespace-pre-wrap">{project.description}</p>
                  </div>
                </>
              )}

              <Separator />

              <div className="flex items-center justify-between">
                <div className="text-xs text-muted-foreground space-y-1">
                  <p>创建时间：{formatDate(project.created_at)}</p>
                  <p>更新时间：{formatDate(project.updated_at)}</p>
                  {project.published_at && (
                    <p>发布时间：{formatDate(project.published_at)}</p>
                  )}
                </div>
                {project.status === 'draft' && (
                  <Button
                    size="sm"
                    onClick={handlePublish}
                    disabled={publishing}
                  >
                    {publishing && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    <Send className="h-4 w-4 mr-1" />
                    发布项目
                  </Button>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="mt-6 flex flex-col items-center justify-center py-8 text-muted-foreground">
            <p>未找到项目详情</p>
          </div>
        )}
      </SheetContent>
    </Sheet>
  )
}

interface ProjectDetailButtonProps {
  project: TenderProject
  onOpenChange: (open: boolean) => void
}

export function ProjectDetailButton({ project: _project, onOpenChange }: ProjectDetailButtonProps) {
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
