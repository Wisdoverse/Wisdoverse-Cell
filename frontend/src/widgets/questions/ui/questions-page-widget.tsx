"use client";

import { useTranslations } from "next-intl";

import { QuestionCard } from "@/features/question-answer";
import { PageHeader } from "@/shared/ui/page-header";
import { QueryBoundary } from "@/shared/ui/query-boundary";
import { useQuestions } from "@/entities/question/model/use-questions";

export function QuestionsPageWidget() {
  const t = useTranslations("questions");
  const { data, error, isLoading, mutate } = useQuestions();

  return (
    <div className="space-y-6">
      <PageHeader title={t("title")} />
      <QueryBoundary
        data={data}
        error={error}
        isLoading={isLoading}
        isEmpty={(questions) => questions.length === 0}
        emptyMessage={t("noQuestions")}
        onRetry={() => mutate()}
      >
        {(questions) => (
          <div className="space-y-4">
            {questions.map((question) => (
              <QuestionCard
                key={question.id}
                question={question}
                onAnswered={() => mutate()}
              />
            ))}
          </div>
        )}
      </QueryBoundary>
    </div>
  );
}
