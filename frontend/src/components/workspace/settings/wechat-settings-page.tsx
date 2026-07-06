"use client";

import {
  CheckCircle2Icon,
  LoaderCircleIcon,
  QrCodeIcon,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/core/auth/AuthProvider";
import {
  useCreateWechatBindCode,
  useStartWechatBotBind,
  useWechatBotBindStatus,
} from "@/core/channels/hooks";
import type { WechatBindCodeResponse } from "@/core/channels/types";
import { useI18n } from "@/core/i18n/hooks";
import { cn } from "@/lib/utils";

import { SettingsSection } from "./settings-section";

export function WechatSettingsPage() {
  const { t } = useI18n();
  const { user } = useAuth();
  const isAdmin = user?.system_role === "admin";
  const { data: bindStatus, isLoading: statusLoading } =
    useWechatBotBindStatus(true);
  const startBind = useStartWechatBotBind();
  const createCode = useCreateWechatBindCode();
  const [code, setCode] = useState<WechatBindCodeResponse | null>(null);

  const status = bindStatus?.status;
  const isPending = status === "pending";
  const isBound = bindStatus?.bound === true;

  return (
    <SettingsSection
      title={t.settings.wechat.title}
      description={t.settings.wechat.description}
    >
      {/* User: link their WeChat to this account */}
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="text-sm font-medium">
              {t.settings.wechat.linkTitle}
            </div>
            <div className="text-muted-foreground text-sm">
              {t.settings.wechat.linkDescription}
            </div>
          </div>
          <Button
            type="button"
            size="sm"
            disabled={createCode.isPending}
            onClick={() => {
              void createCode
                .mutateAsync()
                .then((res) => {
                  setCode(res);
                  toast.success(res.instruction);
                })
                .catch((error) => {
                  toast.error(
                    error instanceof Error
                      ? error.message
                      : t.settings.wechat.linkFailed,
                  );
                });
            }}
          >
            {createCode.isPending ? (
              <LoaderCircleIcon className="animate-spin" />
            ) : (
              <QrCodeIcon />
            )}
            {t.settings.wechat.getCode}
          </Button>
        </div>
        {code ? (
          <div className="bg-muted rounded-md border p-3 text-sm">
            <div className="font-mono text-base font-semibold">
              {`/connect ${code.code}`}
            </div>
            <div className="text-muted-foreground mt-1">
              {t.settings.wechat.codeHint}
            </div>
          </div>
        ) : null}
      </div>

      {/* Admin: bind/rebind the bot */}
      {isAdmin ? (
        <div className="space-y-3 border-t pt-6">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-sm font-medium">
                {t.settings.wechat.botTitle}
                <Badge
                  variant={isBound ? "default" : "outline"}
                  className={cn(!isBound && "text-muted-foreground")}
                >
                  {isBound ? (
                    <CheckCircle2Icon />
                  ) : (
                    <QrCodeIcon />
                  )}
                  {isBound
                    ? t.settings.wechat.bound
                    : isPending
                      ? t.settings.wechat.pending
                      : t.settings.wechat.unbound}
                </Badge>
              </div>
              <div className="text-muted-foreground text-sm">
                {t.settings.wechat.botDescription}
              </div>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={startBind.isPending}
              onClick={() => {
                void startBind
                  .mutateAsync()
                  .then(() => toast.success(t.settings.wechat.bindStarted))
                  .catch((error) => {
                    toast.error(
                      error instanceof Error
                        ? error.message
                        : t.settings.wechat.bindFailed,
                    );
                  });
              }}
            >
              {startBind.isPending ? (
                <LoaderCircleIcon className="animate-spin" />
              ) : (
                <QrCodeIcon />
              )}
              {isBound ? t.settings.wechat.rebind : t.settings.wechat.bind}
            </Button>
          </div>
          {isPending && bindStatus?.qrcode_url ? (
            <a
              href={bindStatus.qrcode_url}
              target="_blank"
              rel="noreferrer"
              className="text-primary inline-flex items-center gap-1 text-sm underline"
            >
              <QrCodeIcon className="size-4" />
              {t.settings.wechat.openQr}
            </a>
          ) : null}
          {isBound && bindStatus?.qrcode_url ? (
            <div className="bg-muted/40 rounded-md border p-3">
              <div className="text-sm font-medium">
                {t.settings.wechat.shareQrTitle}
              </div>
              <div className="text-muted-foreground mt-1 text-sm">
                {t.settings.wechat.shareQrDescription}
              </div>
              <a
                href={bindStatus.qrcode_url}
                target="_blank"
                rel="noreferrer"
                className="text-primary mt-2 inline-flex items-center gap-1 text-sm underline"
              >
                <QrCodeIcon className="size-4" />
                {t.settings.wechat.openShareQr}
              </a>
            </div>
          ) : null}
          {statusLoading ? (
            <div className="text-muted-foreground text-sm">
              {t.common.loading}
            </div>
          ) : null}
        </div>
      ) : null}
    </SettingsSection>
  );
}
