import { useState, useEffect } from 'react'
import { Eye } from 'lucide-react'
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
import { bidderApi, type Bidder } from '@/lib/api'

interface BidderDetailSheetProps {
  bidderId: string | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function BidderDetailSheet({ bidderId, open, onOpenChange }: BidderDetailSheetProps) {
  const [bidder, setBidder] = useState<Bidder | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (bidderId && open) {
      setLoading(true)
      bidderApi.get(bidderId)
        .then(setBidder)
        .catch(console.error)
        .finally(() => setLoading(false))
    } else {
      setBidder(null)
    }
  }, [bidderId, open])

  const formatDate = (date?: string) =>
    date ? new Date(date).toLocaleDateString('zh-CN') : '—'

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="sm:max-w-[500px] overflow-y-auto">
        <SheetHeader>
          <SheetTitle>投标人详情</SheetTitle>
          <SheetDescription>
            {bidder ? `企业名称：${bidder.name}` : '加载中...'}
          </SheetDescription>
        </SheetHeader>

        {loading ? (
          <div className="mt-6 space-y-4">
            <Skeleton className="h-8 w-1/3" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-32 w-full" />
          </div>
        ) : bidder ? (
          <div className="mt-6 space-y-6">
            <div className="space-y-4">
              <div>
                <h3 className="text-lg font-semibold">{bidder.name}</h3>
                <div className="flex items-center gap-2 mt-2 flex-wrap">
                  <Badge>{bidder.status === 'active' ? '正常' : bidder.status}</Badge>
                  {bidder.credit_rating && (
                    <Badge variant="outline">信用评级：{bidder.credit_rating}</Badge>
                  )}
                </div>
              </div>

              <Separator />

              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-muted-foreground">统一信用代码</p>
                  <p className="font-medium">{bidder.unified_credit_code ?? '—'}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">法人代表</p>
                  <p className="font-medium">{bidder.legal_person ?? '—'}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">联系人</p>
                  <p className="font-medium">{bidder.contact_person ?? '—'}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">联系电话</p>
                  <p className="font-medium">{bidder.phone ?? '—'}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">电子邮箱</p>
                  <p className="font-medium">{bidder.email ?? '—'}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">所在地区</p>
                  <p className="font-medium">{bidder.region ?? '—'}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">注册日期</p>
                  <p className="font-medium">{formatDate(bidder.registration_date)}</p>
                </div>
              </div>

              {bidder.address && (
                <>
                  <Separator />
                  <div>
                    <p className="text-muted-foreground mb-1">详细地址</p>
                    <p className="text-sm">{bidder.address}</p>
                  </div>
                </>
              )}

              {bidder.business_scope && (
                <>
                  <Separator />
                  <div>
                    <p className="text-muted-foreground mb-1">经营范围</p>
                    <p className="text-sm whitespace-pre-wrap">{bidder.business_scope}</p>
                  </div>
                </>
              )}

              {bidder.remark && (
                <>
                  <Separator />
                  <div>
                    <p className="text-muted-foreground mb-1">备注</p>
                    <p className="text-sm whitespace-pre-wrap">{bidder.remark}</p>
                  </div>
                </>
              )}

              <Separator />

              <div className="text-xs text-muted-foreground space-y-1">
                <p>创建时间：{formatDate(bidder.created_at)}</p>
                <p>更新时间：{formatDate(bidder.updated_at)}</p>
              </div>
            </div>
          </div>
        ) : (
          <div className="mt-6 flex flex-col items-center justify-center py-8 text-muted-foreground">
            <p>未找到投标人详情</p>
          </div>
        )}
      </SheetContent>
    </Sheet>
  )
}

interface BidderDetailButtonProps {
  bidder: Bidder
  onOpenChange: (open: boolean) => void
}

export function BidderDetailButton({ bidder: _bidder, onOpenChange }: BidderDetailButtonProps) {
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
