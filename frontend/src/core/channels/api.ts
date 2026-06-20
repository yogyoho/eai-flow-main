import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

import type {
  ChannelConnectResponse,
  ChannelConnection,
  ChannelConnectionsResponse,
  ChannelProviderId,
  ChannelProvider,
  ChannelProvidersResponse,
  ChannelRuntimeConfigValues,
  WechatBindCodeResponse,
  WechatBotBindStatus,
} from "./types";

function channelsUrl(path: string): string {
  return `${getBackendBaseURL()}/api/channels${path}`;
}

async function throwChannelApiError(
  response: Response,
  fallback: string,
): Promise<never> {
  const body = (await response.json().catch(() => ({}))) as {
    detail?: unknown;
  };
  throw new Error(typeof body.detail === "string" ? body.detail : fallback);
}

export async function listChannelProviders(): Promise<ChannelProvidersResponse> {
  const response = await fetch(channelsUrl("/providers"));
  if (!response.ok) {
    await throwChannelApiError(
      response,
      `Failed to load channel providers: ${response.statusText}`,
    );
  }
  return response.json() as Promise<ChannelProvidersResponse>;
}

export async function listChannelConnections(): Promise<ChannelConnection[]> {
  const response = await fetch(channelsUrl("/connections"));
  if (!response.ok) {
    await throwChannelApiError(
      response,
      `Failed to load channel connections: ${response.statusText}`,
    );
  }
  const data = (await response.json()) as ChannelConnectionsResponse;
  return data.connections;
}

export async function connectChannelProvider(
  provider: ChannelProviderId,
): Promise<ChannelConnectResponse> {
  const response = await fetch(
    channelsUrl(`/${encodeURIComponent(provider)}/connect`),
    { method: "POST" },
  );
  if (!response.ok) {
    await throwChannelApiError(
      response,
      `Failed to connect ${provider}: ${response.statusText}`,
    );
  }
  return response.json() as Promise<ChannelConnectResponse>;
}

export async function configureChannelProvider(
  provider: ChannelProviderId,
  values: ChannelRuntimeConfigValues,
): Promise<ChannelProvider> {
  const response = await fetch(
    channelsUrl(`/${encodeURIComponent(provider)}/runtime-config`),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ values }),
    },
  );
  if (!response.ok) {
    await throwChannelApiError(
      response,
      `Failed to configure ${provider}: ${response.statusText}`,
    );
  }
  return response.json() as Promise<ChannelProvider>;
}

export async function disconnectChannelConnection(
  connectionId: string,
): Promise<void> {
  const response = await fetch(
    channelsUrl(`/connections/${encodeURIComponent(connectionId)}`),
    { method: "DELETE" },
  );
  if (!response.ok) {
    await throwChannelApiError(
      response,
      `Failed to disconnect channel: ${response.statusText}`,
    );
  }
}

export async function disconnectChannelProvider(
  provider: ChannelProviderId,
): Promise<ChannelProvider> {
  const response = await fetch(
    channelsUrl(`/${encodeURIComponent(provider)}/runtime-config`),
    { method: "DELETE" },
  );
  if (!response.ok) {
    await throwChannelApiError(
      response,
      `Failed to disconnect ${provider}: ${response.statusText}`,
    );
  }
  return response.json() as Promise<ChannelProvider>;
}

// -- WeChat iLink system bot (admin bind + user binding-code) ---------------

function wechatBotUrl(path: string): string {
  return `${getBackendBaseURL()}/api/channels/wechat-bot${path}`;
}

export async function startWechatBotBind(): Promise<{ status: string }> {
  const response = await fetch(wechatBotUrl("/bind"), { method: "POST" });
  if (!response.ok) {
    await throwChannelApiError(
      response,
      `Failed to start WeChat bind: ${response.statusText}`,
    );
  }
  return response.json() as Promise<{ status: string }>;
}

export async function getWechatBotBindStatus(): Promise<WechatBotBindStatus> {
  const response = await fetch(wechatBotUrl("/bind/status"));
  if (!response.ok) {
    await throwChannelApiError(
      response,
      `Failed to read WeChat bind status: ${response.statusText}`,
    );
  }
  return response.json() as Promise<WechatBotBindStatus>;
}

export async function createWechatBindCode(): Promise<WechatBindCodeResponse> {
  const response = await fetch(wechatBotUrl("/bind-code"), { method: "POST" });
  if (!response.ok) {
    await throwChannelApiError(
      response,
      `Failed to create WeChat binding code: ${response.statusText}`,
    );
  }
  return response.json() as Promise<WechatBindCodeResponse>;
}
