"use client";

import Link from "next/link";
import { useTranslations, useLocale } from "next-intl";
import { FileQuestion, Home } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";

export default function NotFoundPage() {
  const t = useTranslations("notFoundPage");
  const locale = useLocale();

  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <Card className="w-full max-w-md text-center">
        <CardHeader>
          <div className="mx-auto mb-2 flex size-12 items-center justify-center rounded-full bg-muted">
            <FileQuestion className="size-6 text-muted-foreground" />
          </div>
          <p className="text-5xl font-bold text-muted-foreground">
            {t("code")}
          </p>
          <CardTitle className="text-xl">{t("title")}</CardTitle>
          <CardDescription>{t("description")}</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">{t("suggestion")}</p>
        </CardContent>
        <CardFooter className="flex justify-center">
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
