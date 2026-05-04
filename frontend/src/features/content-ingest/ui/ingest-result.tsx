"use client";

import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { CheckCircle2 } from "lucide-react";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  CardFooter,
} from "@/shared/ui/card";
import { Button } from "@/shared/ui/button";
import type { IngestResponse } from "@/lib/api/types";

interface IngestResultProps {
  result: IngestResponse;
}

export function IngestResult({ result }: IngestResultProps) {
  const t = useTranslations("ingest");
  const tn = useTranslations("nav");
  const locale = useLocale();
  const router = useRouter();

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CheckCircle2 className="h-5 w-5 text-green-500" />
          {t("success", { count: result.requirements_extracted })}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <dt className="text-muted-foreground">{tn("requirements")}</dt>
            <dd className="text-2xl font-semibold">
              {result.requirements_extracted}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">{tn("questions")}</dt>
            <dd className="text-2xl font-semibold">
              {result.questions_generated}
            </dd>
          </div>
        </dl>
      </CardContent>
      <CardFooter className="gap-2">
        <Button onClick={() => router.push(`/${locale}/requirements`)}>
          {t("viewRequirements")}
        </Button>
        <Button variant="outline" onClick={() => router.push(`/${locale}/questions`)}>
          {t("viewQuestions")}
        </Button>
      </CardFooter>
    </Card>
  );
}
