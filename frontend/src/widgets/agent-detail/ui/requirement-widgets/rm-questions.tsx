"use client";

import { useQuestions } from "@/entities/question";
import { QuestionCard } from "@/features/question-answer";

export default function RmQuestionsWidget() {
  const { data: questions, isLoading, mutate } = useQuestions();

  if (isLoading) {
    return (
      <div className="text-sm text-muted-foreground py-8 text-center">
        Loading questions...
      </div>
    );
  }

  if (!questions || questions.length === 0) {
    return (
      <div className="text-sm text-muted-foreground py-8 text-center">
        No open questions
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {questions.map((q) => (
        <QuestionCard key={q.id} question={q} onAnswered={() => mutate()} />
      ))}
    </div>
  );
}
