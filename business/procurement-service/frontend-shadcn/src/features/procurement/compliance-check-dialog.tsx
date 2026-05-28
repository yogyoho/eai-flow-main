import { useState, type ReactNode } from 'react'
import { CheckCircle2, XCircle, Loader2, ShieldCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { bidApi, type Bid } from '@/lib/api'
import { toast } from 'sonner'

interface ComplianceCheckDialogProps {
  bid: Bid
  onSuccess?: () => void
  children?: ReactNode
}

interface CheckResult {
  passed: boolean
  score: number
  issues: unknown[]
}

export function ComplianceCheckDialog({ bid, onSuccess, children }: ComplianceCheckDialogProps) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<CheckResult | null>(null)

  const handleCheck = async () => {
    setLoading(true)
    setResult(null)
    try {
      const checkResult = await bidApi.complianceCheck(bid.id)
      setResult(checkResult)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '合规检查失败')
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
            合规检查
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>投标合规检查</DialogTitle>
          <DialogDescription>
            对投标记录进行合规性检查，包括时间、价格、文档等
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="text-sm text-muted-foreground">
            <p>投标编号：{bid.bid_no}</p>
            <p>投标报价：{bid.bid_price ? `¥${Number(bid.bid_price).toLocaleString('zh-CN')}` : '—'}</p>
          </div>

          {!result && (
            <Button onClick={handleCheck} disabled={loading} className="w-full">
              {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              开始检查
            </Button>
          )}

          {loading && !result && (
            <div className="text-center py-4 text-muted-foreground">
              正在检查投标合规性，请稍候...
            </div>
          )}

          {result && (
            <div className="space-y-4">
              <Alert variant={result.passed ? "default" : "destructive"}>
                {result.passed ? (
                  <CheckCircle2 className="h-4 w-4" />
                ) : (
                  <XCircle className="h-4 w-4" />
                )}
                <AlertTitle>
                  {result.passed ? '合规检查通过' : '合规检查未通过'}
                </AlertTitle>
                <AlertDescription>
                  合规评分：{result.score}分
                </AlertDescription>
              </Alert>

              {result.issues && result.issues.length > 0 && (
                <div className="space-y-2">
                  <h4 className="font-medium text-sm">问题详情：</h4>
                  <ul className="text-sm space-y-1 list-disc list-inside">
                    {result.issues.map((issue, index) => (
                      <li key={index} className="text-muted-foreground">
                        {String(issue)}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="flex gap-2">
                <Button variant="outline" onClick={handleCheck} disabled={loading} className="flex-1">
                  重新检查
                </Button>
                <Button onClick={() => { setOpen(false); onSuccess?.() }} className="flex-1">
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
