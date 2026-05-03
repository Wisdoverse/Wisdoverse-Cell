"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";
import { Badge } from "@/shared/ui/badge";
import { Skeleton } from "@/shared/ui/skeleton";
import { Copy } from "lucide-react";
import { getSimilarRequirements } from "@/lib/api/requirements";
import { StatusBadge } from "@/components/shared/status-badge";

interface SimilarRequirementsProps {
  requirementId: string;
}

export function SimilarRequirements({
  requirementId,
}: SimilarRequirementsProps) {
  const t = useTranslations("requirements");
  const router = useRouter();
  const { data, isLoading } = useSWR(
    ["similar", requirementId],
    () => getSimilarRequirements(requirementId, 5),
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Copy className="h-4 w-4" />
          {t("similarRequirements")}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        ) : !data || data.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("noSimilar")}</p>
        ) : (
          <div className="space-y-2">
            {data.map((item) => (
              <div
                key={item.requirement.id}
                className="flex cursor-pointer items-start justify-between rounded-lg border p-3 transition-colors hover:bg-muted/50"
                onClick={() =>
                  router.push(`../requirements/${item.requirement.id}`)
                }
              >
                <div className="space-y-1 flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">
                    {item.requirement.title}
                  </p>
                  <StatusBadge status={item.requirement.status} />
                </div>
                <Badge variant="outline" className="ml-2 shrink-0">
                  {t("similarity")} {Math.round(item.similarity * 100)}%
                </Badge>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
