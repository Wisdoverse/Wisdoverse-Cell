"use client";

import { useLocale, useTranslations } from "next-intl";
import useSWR from "swr";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";
import { Skeleton } from "@/shared/ui/skeleton";
import { MessageSquare } from "lucide-react";
import { getContext } from "@/lib/api/requirements";

interface ContextMessagesProps {
  requirementId: string;
}

export function ContextMessages({ requirementId }: ContextMessagesProps) {
  const t = useTranslations("requirements");
  const locale = useLocale();
  const { data, isLoading, error } = useSWR(["context", requirementId], () =>
    getContext(requirementId),
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
          <p className="text-muted-foreground text-sm">{t("noContext")}</p>
        ) : (
          <div className="space-y-3">
            {data.map((message) => (
              <div key={message.id} className="space-y-1 rounded-lg border p-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">{message.sender_name}</span>
                  <span className="text-muted-foreground text-xs">
                    {new Intl.DateTimeFormat(locale, {
                      dateStyle: "medium",
                      timeStyle: "short",
                    }).format(new Date(message.sent_at))}
                  </span>
                </div>
                <p className="text-muted-foreground text-sm whitespace-pre-wrap">
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
