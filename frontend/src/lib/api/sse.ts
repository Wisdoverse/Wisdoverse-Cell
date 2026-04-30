"use client";

import { useEffect, useRef, useCallback } from "react";
import { mutate } from "swr";
import { toast } from "sonner";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "/api/v1";
const SSE_URL = `${API_BASE}/events/stream`;

const MAX_RECONNECT_DELAY = 30_000; // 30 seconds
const INITIAL_RECONNECT_DELAY = 1_000; // 1 second
const MAX_RETRY_ATTEMPTS = 20;

type EventType =
  | "requirement.confirmed"
  | "requirement.rejected"
  | "requirement.extracted"
  | "circuit-breaker.state-change"
  | "agent.status-change"
  | "agent.health-update"
  | "approval.requested"
  | "approval.resolved"
  | "activity.new";

interface SSEEvent {
  type: EventType;
  data: Record<string, unknown>;
}

// Declarative mapping: event type -> SWR cache key patterns to invalidate.
// Patterns match against actual SWR keys (strings like "stats" or arrays like ["requirements", ...]).
const INVALIDATION_MAP: Record<EventType, string[]> = {
  "requirement.confirmed": ["requirements", "stats"],
  "requirement.rejected": ["requirements", "stats"],
  "requirement.extracted": ["requirements", "open-questions", "stats"],
  "circuit-breaker.state-change": ["circuit-breaker", "health-ready"],
  "agent.status-change": ["agents", "agent-detail"],
  "agent.health-update": ["agents", "agent-detail"],
  "approval.requested": ["approvals"],
  "approval.resolved": ["approvals"],
  "activity.new": ["activity"],
};

function keyMatchesPattern(key: unknown, pattern: string): boolean {
  if (typeof key === "string") return key.includes(pattern);
  if (Array.isArray(key)) return key.some((k) => typeof k === "string" && k.includes(pattern));
  return false;
}

function invalidateCaches(eventType: EventType) {
  const patterns = INVALIDATION_MAP[eventType];
  if (!patterns) return;
  for (const pattern of patterns) {
    mutate(
      (key: unknown) => keyMatchesPattern(key, pattern),
      undefined,
      { revalidate: true },
    );
  }
}

interface UseEventStreamOptions {
  /** Translation function for toast messages */
  getToastMessage?: (eventType: EventType) => string;
  /** Called when max reconnection attempts are exhausted */
  onDisconnected?: () => void;
  /** Whether the hook should be active */
  enabled?: boolean;
}

/**
 * Hook that connects to the SSE endpoint for real-time event streaming.
 * Automatically reconnects with exponential backoff on disconnection.
 * Gracefully handles unavailable endpoints.
 */
export function useEventStream(options: UseEventStreamOptions = {}) {
  const { getToastMessage, onDisconnected, enabled = true } = options;
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const handleEvent = useCallback(
    (event: MessageEvent) => {
      let parsed: SSEEvent;
      try {
        parsed = JSON.parse(event.data);
      } catch {
        console.warn("[sse] Received malformed SSE event data:", event.data);
        return;
      }

      try {
        invalidateCaches(parsed.type);

        // Show contextual toast notifications for new event types
        switch (parsed.type) {
          case "agent.status-change": {
            const name = (parsed.data.agent_name as string) || "Agent";
            const status = (parsed.data.status as string) || "unknown";
            toast.info(`${name}: status changed to ${status}`);
            break;
          }
          case "approval.requested": {
            const title = (parsed.data.title as string) || "Untitled";
            toast.info(`New approval request: ${title}`);
            break;
          }
          case "approval.resolved": {
            const outcome = (parsed.data.outcome as string) || "unknown";
            toast.info(`Approval resolved: ${outcome}`);
            break;
          }
          default: {
            if (getToastMessage) {
              const message = getToastMessage(parsed.type);
              if (message) {
                toast.info(message);
              }
            }
          }
        }
      } catch (err) {
        console.error("[sse] Error processing SSE event:", parsed.type, err);
      }
    },
    [getToastMessage],
  );

  useEffect(() => {
    mountedRef.current = true;

    if (!enabled) return;

    let reconnectAttempt = 0;

    function connect() {
      if (!mountedRef.current) return;

      // Clean up existing connection
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }

      try {
        const eventSource = new EventSource(SSE_URL, {
          withCredentials: true,
        });

        eventSource.onopen = () => {
          reconnectAttempt = 0;
        };

        for (const eventType of Object.keys(INVALIDATION_MAP) as EventType[]) {
          eventSource.addEventListener(eventType, handleEvent);
        }

        eventSource.onerror = () => {
          eventSource.close();
          eventSourceRef.current = null;

          if (!mountedRef.current) return;

          reconnectAttempt += 1;

          if (reconnectAttempt === 1) {
            console.warn("[sse] Connection lost, attempting to reconnect...");
          } else if (reconnectAttempt % 5 === 0) {
            console.warn(`[sse] Reconnection attempt ${reconnectAttempt}/${MAX_RETRY_ATTEMPTS}`);
          }

          if (reconnectAttempt >= MAX_RETRY_ATTEMPTS) {
            console.warn(
              `[sse] Giving up after ${MAX_RETRY_ATTEMPTS} reconnection attempts`,
            );
            onDisconnected?.();
            return;
          }

          const delay = Math.min(
            INITIAL_RECONNECT_DELAY * Math.pow(2, reconnectAttempt - 1),
            MAX_RECONNECT_DELAY,
          );

          reconnectTimerRef.current = setTimeout(() => {
            if (mountedRef.current) {
              connect();
            }
          }, delay);
        };

        eventSourceRef.current = eventSource;
      } catch (err) {
        console.error("[sse] Failed to create EventSource connection:", err);
      }
    }

    connect();

    return () => {
      mountedRef.current = false;
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, [enabled, handleEvent, onDisconnected]);
}
