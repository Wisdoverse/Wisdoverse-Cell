"use client";

import { useTranslations } from "next-intl";
import useSWR from "swr";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { MessageSquare } from "lucide-react";
import { getContext } from "@/lib/api/requirements";

interface ContextMessagesProps {
  requirementId: string;
}

export function ContextMessages({ requirementId }: ContextMessagesProps) {
  const t = useTranslations("requirements");
  const { data, isLoading, error } = useSWR(
    ["context", requirementId],
    () => getContext(requirementId),
  );

  if (error) {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <MessageSquare className="h-4 w-4" />
          {t("contextMessages")}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : !data || data.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("noContext")}</p>
        ) : (
          <div className="space-y-3">
            {data.map((message) => (
              <div
                key={message.id}
                className="rounded-lg border p-3 space-y-1"
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">
                    {message.sender_name}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {new Date(message.sent_at).toLocaleString()}
                  </span>
                </div>
                <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                  {message.content}
                </p>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
