"use client";

import { useSession } from "next-auth/react";
import { useTranslations } from "next-intl";
import { useCallback } from "react";
import { toast } from "sonner";
import { useEventStream } from "@/lib/api/sse";

/**
 * Invisible component that mounts the SSE event stream.
 * Only activates when the user is authenticated.
 * Renders nothing - exists solely for side effects.
 */
export function EventListener() {
  const { status } = useSession();
  const t = useTranslations("events");
  const tCommon = useTranslations("common");

  const onDisconnected = useCallback(() => {
    toast.warning(tCommon("sseDisconnected"));
  }, [tCommon]);

  const getToastMessage = useCallback(
    (eventType: string): string => {
      switch (eventType) {
        case "requirement.confirmed":
          return t("requirementConfirmed");
        case "requirement.rejected":
          return t("requirementRejected");
        case "requirement.extracted":
          return t("requirementExtracted");
        case "circuit-breaker.state-change":
          return t("circuitBreakerStateChange");
        default:
          return "";
      }
    },
    [t],
  );

  useEventStream({
    enabled: status === "authenticated",
    getToastMessage,
    onDisconnected,
  });

  return null;
}
