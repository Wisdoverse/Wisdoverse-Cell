import { apiClient } from "./client";
import type {
  MessageSearchParams,
  MessageSearchResult,
  MessageSession,
} from "./types";

export function searchMessages(
  params: MessageSearchParams = {},
): Promise<MessageSearchResult[]> {
  return apiClient.get<MessageSearchResult[]>("/messages/search", params);
}

export function getSession(sessionId: string): Promise<MessageSession> {
  return apiClient.get<MessageSession>(`/messages/session/${sessionId}`);
}
