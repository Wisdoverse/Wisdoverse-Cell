"use client";

import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { AnswerForm } from "@/components/questions/answer-form";
import type { OpenQuestion } from "@/lib/api/types";

interface QuestionCardProps {
  question: OpenQuestion;
  onAnswered: () => void;
}

export function QuestionCard({ question, onAnswered }: QuestionCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{question.question}</CardTitle>
        {question.context && (
          <CardDescription>{question.context}</CardDescription>
        )}
      </CardHeader>
      <CardContent>
        <AnswerForm questionId={question.id} onSuccess={onAnswered} />
      </CardContent>
    </Card>
  );
}
