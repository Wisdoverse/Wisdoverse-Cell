"use client";

import { CalendarClock } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";

import {
  Card,
  CardAction,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/shared/ui/card";
import { Badge } from "@/shared/ui/badge";
import { AnswerForm } from "./answer-form";
import type { OpenQuestion } from "@/lib/api/types";

interface QuestionCardProps {
  question: OpenQuestion;
  onAnswered: () => void;
}

function formatDate(dateStr: string, locale: string): string {
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat(locale, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function QuestionCard({ question, onAnswered }: QuestionCardProps) {
  const t = useTranslations("questions");
  const locale = useLocale();

  return (
    <Card className="rounded-lg">
      <CardHeader>
        <CardTitle className="text-base leading-snug">
          {question.question}
        </CardTitle>
        <CardAction>
          <Badge variant="secondary" className="rounded-md">
            {t(`statusLabels.${question.status}`)}
          </Badge>
        </CardAction>
        {question.context && (
          <CardDescription className="max-w-3xl">
            <span className="font-medium text-foreground">
              {t("contextLabel")}:
            </span>{" "}
            {question.context}
          </CardDescription>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="text-muted-foreground flex items-center gap-2 text-xs">
          <CalendarClock className="size-3.5" />
          <span>{t("askedAt", { time: formatDate(question.created_at, locale) })}</span>
        </div>
        <AnswerForm questionId={question.id} onSuccess={onAnswered} />
      </CardContent>
    </Card>
  );
}
