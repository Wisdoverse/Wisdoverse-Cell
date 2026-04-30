"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useTranslations, useLocale } from "next-intl";
import { AlertCircle, RotateCcw, Home } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const t = useTranslations("errorPage");
  const tCommon = useTranslations("common");
  const locale = useLocale();

  useEffect(() => {
    console.error("[ErrorBoundary]", error.digest, error);
    import("@sentry/nextjs")
      .then((Sentry) => Sentry.captureException(error))
      .catch((err) => console.warn("[ErrorBoundary] Failed to load Sentry:", err));
  }, [error]);

  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <Card className="w-full max-w-md text-center">
        <CardHeader>
          <div className="mx-auto mb-2 flex size-12 items-center justify-center rounded-full bg-destructive/10">
            <AlertCircle className="size-6 text-destructive" />
          </div>
          <CardTitle className="text-xl">{t("title")}</CardTitle>
          <CardDescription>{t("description")}</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-muted-foreground">
            {tCommon("appName")}
          </p>
          {error.digest && (
            <p className="text-xs text-muted-foreground mt-2">
              Error ID: {error.digest}
            </p>
          )}
        </CardContent>
        <CardFooter className="flex justify-center gap-3">
          <Button variant="outline" onClick={reset}>
            <RotateCcw className="size-4" />
            {t("retry")}
          </Button>
          <Button asChild>
            <Link href={`/${locale}/dashboard`}>
              <Home className="size-4" />
              {t("goToDashboard")}
            </Link>
          </Button>
        </CardFooter>
      </Card>
    </div>
  );
}
