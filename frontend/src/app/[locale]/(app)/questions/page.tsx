"use client";

import { useTranslations } from "next-intl";
import { PageHeader } from "@/components/shared/page-header";
import { QuestionCard } from "@/components/questions/question-card";
import { QueryBoundary } from "@/components/shared/query-boundary";
import { useQuestions } from "@/lib/hooks/use-questions";

export default function QuestionsPage() {
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
