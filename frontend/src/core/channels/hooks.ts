import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  configureChannelProvider,
  connectChannelProvider,
  createWechatBindCode,
  disconnectChannelConnection,
  disconnectChannelProvider,
  getWechatBotBindStatus,
  listChannelConnections,
  listChannelProviders,
  startWechatBotBind,
} from "./api";
import type { ChannelProviderId, ChannelRuntimeConfigValues } from "./types";

export const channelProviderQueryKey = ["channelProviders"] as const;
export const channelConnectionsQueryKey = ["channelConnections"] as const;

export function useChannelProviders() {
  const { data, isLoading, error } = useQuery({
    queryKey: channelProviderQueryKey,
    queryFn: () => listChannelProviders(),
  });
  return {
    enabled: data?.enabled ?? false,
    providers: data?.providers ?? [],
    isLoading,
    error,
  };
}

export function useChannelConnections() {
  const { data, isLoading, error } = useQuery({
    queryKey: channelConnectionsQueryKey,
    queryFn: () => listChannelConnections(),
  });
  return { connections: data ?? [], isLoading, error };
}

export function useConnectChannelProvider() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (provider: ChannelProviderId) =>
      connectChannelProvider(provider),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: channelProviderQueryKey });
      void queryClient.invalidateQueries({
        queryKey: channelConnectionsQueryKey,
      });
    },
  });
}

export function useConfigureChannelProvider() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      provider,
      values,
    }: {
      provider: ChannelProviderId;
      values: ChannelRuntimeConfigValues;
    }) => configureChannelProvider(provider, values),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: channelProviderQueryKey });
      void queryClient.invalidateQueries({
        queryKey: channelConnectionsQueryKey,
      });
    },
  });
}

export function useDisconnectChannelConnection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (connectionId: string) =>
      disconnectChannelConnection(connectionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: channelProviderQueryKey });
      void queryClient.invalidateQueries({
        queryKey: channelConnectionsQueryKey,
      });
    },
  });
}

export function useDisconnectChannelProvider() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (provider: ChannelProviderId) =>
      disconnectChannelProvider(provider),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: channelProviderQueryKey });
      void queryClient.invalidateQueries({
        queryKey: channelConnectionsQueryKey,
      });
    },
  });
}

// -- WeChat iLink system bot (admin bind + user binding-code) ---------------

export const wechatBotBindStatusQueryKey = ["wechatBotBindStatus"] as const;

export function useStartWechatBotBind() {
  return useMutation({ mutationFn: () => startWechatBotBind() });
}

export function useWechatBotBindStatus(enabled: boolean) {
  return useQuery({
    queryKey: wechatBotBindStatusQueryKey,
    queryFn: () => getWechatBotBindStatus(),
    enabled,
    // Poll every 2s while a bind is pending; stop once it resolves.
    refetchInterval: (query) => (query.state.data?.status === "pending" ? 2000 : false),
  });
}

export function useCreateWechatBindCode() {
  return useMutation({ mutationFn: () => createWechatBindCode() });
}
