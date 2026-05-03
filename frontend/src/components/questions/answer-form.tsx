"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";
import { Button } from "@/shared/ui/button";
import { Textarea } from "@/shared/ui/textarea";
import { answerQuestion } from "@/lib/api/export";

interface AnswerFormProps {
  questionId: string;
  onSuccess: () => void;
}

export function AnswerForm({ questionId, onSuccess }: AnswerFormProps) {
  const t = useTranslations("questions");
  const tc = useTranslations("common");
  const [answer, setAnswer] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!answer.trim()) return;

    setLoading(true);
    try {
      await answerQuestion(questionId, answer.trim());
      toast.success(t("answerSuccess"));
      setAnswer("");
      onSuccess();
    } catch (err) {
      console.error("[answer-form] Failed to submit answer:", err);
      toast.error(tc("error"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <Textarea
        placeholder={t("answerPlaceholder")}
        value={answer}
        onChange={(e) => setAnswer(e.target.value)}
        rows={3}
      />
      <Button
        type="submit"
        size="sm"
        disabled={loading || !answer.trim()}
      >
        {loading ? tc("loading") : t("submitAnswer")}
      </Button>
    </form>
  );
}
