"use client";

import { useMutation, useQuery } from "@tanstack/react-query";

import { conversationApi } from "../api";
import type { Conversation, ConversationListResponse } from "../types";

export function useUserConversations(params?: {
  skip?: number;
  limit?: number;
  status?: string;
}) {
  return useQuery<ConversationListResponse>({
    queryKey: ["user-conversations", params],
    queryFn: async () => {
      return conversationApi.list(params);
    },
  });
}

export function useUserConversation(threadId: string) {
  return useQuery<Conversation>({
    queryKey: ["user-conversation", threadId],
    queryFn: async () => {
      return conversationApi.get(threadId);
    },
    enabled: !!threadId,
  });
}

export function useCreateConversation() {
  return useMutation({
    mutationFn: async (data?: { title?: string }) => {
      return conversationApi.create(data);
    },
  });
}
