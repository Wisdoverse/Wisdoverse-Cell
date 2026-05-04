"use client";

import { Skeleton } from "@/shared/ui/skeleton";
import { Button } from "@/shared/ui/button";
import { AlertCircle, RefreshCw } from "lucide-react";
import { useTranslations } from "next-intl";

interface QueryBoundaryProps<T> {
  data: T | undefined;
  error: Error | undefined;
  isLoading: boolean;
  isEmpty?: (data: T) => boolean;
  skeleton?: React.ReactNode;
  emptyMessage?: string;
  onRetry?: () => void;
  children: (data: T) => React.ReactNode;
}

export function QueryBoundary<T>({
  data,
  error,
  isLoading,
  isEmpty,
  skeleton,
  emptyMessage,
  onRetry,
  children,
}: QueryBoundaryProps<T>) {
  const t = useTranslations("common");

  if (isLoading) {
    return skeleton || <DefaultSkeleton />;
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
        <AlertCircle className="h-10 w-10 mb-4 text-destructive" />
        <p className="text-sm mb-4">{t("error")}</p>
        {onRetry && (
          <Button variant="outline" size="sm" onClick={onRetry}>
            <RefreshCw className="h-4 w-4 mr-2" />
            {t("retry")}
          </Button>
        )}
      </div>
    );
  }

  if (!data || (isEmpty && isEmpty(data))) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
        <p className="text-sm">{emptyMessage || t("noData")}</p>
      </div>
    );
  }

  return <>{children(data)}</>;
}

function DefaultSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-8 w-1/3" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-2/3" />
      <Skeleton className="h-4 w-full" />
    </div>
  );
}
