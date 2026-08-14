"use client";

import {
  CheckCircle2Icon,
  LoaderCircleIcon,
  QrCodeIcon,
  RefreshCwIcon,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/core/auth/AuthProvider";
import {
  useConnectChannelProvider,
  useRestartWechatChannel,
  useWechatBotStatus,
} from "@/core/channels/hooks";
import type { ChannelConnectResponse } from "@/core/channels/types";
import { useI18n } from "@/core/i18n/hooks";

import { SettingsSection } from "./settings-section";

// EAI-CUSTOM: ClawBot activation card. Surfaces the bot-activation QR + status
// read from the gateway auth-state file so users can scan to activate without
// digging through logs. Regenerate is admin-only (POST /wechat/restart).
function BotStatusCard() {
  const { t } = useI18n();
  const { user } = useAuth();
  const isAdmin = user?.system_role === "admin";
  const { status, isLoading } = useWechatBotStatus();
  const restart = useRestartWechatChannel();

  // QR-login disabled: the operator must configure bot_token instead.
  if (status && !status.qrcode_login_enabled) {
    return (
      <div className="bg-muted space-y-1 rounded-md border p-3 text-sm">
        <div className="font-medium">{t.settings.wechat.botStatusTitle}</div>
        <div className="text-muted-foreground">
          {t.settings.wechat.botQrLoginDisabled}
        </div>
      </div>
    );
  }

  const confirmed = status?.bot_bound === true;
  // A lingering bot_token means the bot is activated even if the QR-flow
  // status is stale (expired/timeout); don't show a stale QR in that case.
  const pending = !confirmed && status?.status === "pending";
  const expiredLike =
    status?.status === "expired" || status?.status === "timeout";

  return (
    <div className="bg-muted space-y-3 rounded-md border p-3 text-sm">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="font-medium">{t.settings.wechat.botStatusTitle}</div>
          <div className="text-muted-foreground mt-0.5">
            {confirmed
              ? t.settings.wechat.botActive
              : pending
                ? t.settings.wechat.botPending
                : expiredLike
                  ? t.settings.wechat.botExpired
                  : t.settings.wechat.botNeedsActivation}
          </div>
        </div>
        {isLoading ? (
          <LoaderCircleIcon className="text-muted-foreground h-4 w-4 animate-spin" />
        ) : confirmed ? (
          <CheckCircle2Icon className="h-5 w-5 text-emerald-500" />
        ) : (
          <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-amber-500" />
        )}
      </div>

      {pending && status?.qrcode_url ? (
        <div className="flex flex-col items-center gap-2 py-1">
          <img
            alt="WeChat ClawBot QR"
            src={status.qrcode_url}
            className="h-48 w-48 rounded-md border bg-white"
          />
          <div className="text-muted-foreground text-xs">
            {t.settings.wechat.botScanHint}
          </div>
        </div>
      ) : null}

      {!confirmed && !pending ? (
        <div className="flex items-center justify-end gap-3">
          {!isAdmin ? (
            <div className="text-muted-foreground text-xs">
              {t.settings.wechat.botAskAdmin}
            </div>
          ) : null}
          {isAdmin ? (
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={restart.isPending}
              onClick={() => {
                void restart
                  .mutateAsync()
                  .then((res) => {
                    toast.success(res.message);
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
              {restart.isPending ? (
                <LoaderCircleIcon className="animate-spin" />
              ) : (
                <RefreshCwIcon />
              )}
              {restart.isPending
                ? t.settings.wechat.botRegenerating
                : t.settings.wechat.botRegenerate}
            </Button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function WechatSettingsPage() {
  const { t } = useI18n();
  const connect = useConnectChannelProvider();
  const [result, setResult] = useState<ChannelConnectResponse | null>(null);

  return (
    <SettingsSection
      title={t.settings.wechat.title}
      description={t.settings.wechat.description}
    >
      <div className="space-y-4">
        <BotStatusCard />

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
              disabled={connect.isPending}
              onClick={() => {
                void connect
                  .mutateAsync("wechat")
                  .then((res) => {
                    setResult(res);
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
              {connect.isPending ? (
                <LoaderCircleIcon className="animate-spin" />
              ) : (
                <QrCodeIcon />
              )}
              {t.settings.wechat.getCode}
            </Button>
          </div>
          {result ? (
            <div className="bg-muted rounded-md border p-3 text-sm">
              <div className="font-mono text-base font-semibold">
                {`/connect ${result.code}`}
              </div>
              <div className="text-muted-foreground mt-1">
                {t.settings.wechat.codeHint}
              </div>
            </div>
          ) : null}
          <div className="text-muted-foreground text-xs">
            {t.settings.wechat.addBotHint}
          </div>
        </div>
      </div>
    </SettingsSection>
  );
}
