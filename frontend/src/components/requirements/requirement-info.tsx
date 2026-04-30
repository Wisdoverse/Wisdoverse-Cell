"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { ChevronDown, ChevronRight, MessageCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { StatusBadge } from "@/components/shared/status-badge";
import { PriorityBadge } from "@/components/shared/priority-badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import type { Requirement } from "@/lib/api/types";

interface RequirementInfoProps {
  requirement: Requirement;
}

export function RequirementInfo({ requirement }: RequirementInfoProps) {
  const t = useTranslations("requirements");
  const [questionsOpen, setQuestionsOpen] = useState(false);

  return (
    <div className="space-y-6">
      {/* Description */}
      <Card>
        <CardHeader>
          <CardTitle>{t("description")}</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm leading-relaxed whitespace-pre-wrap">
            {requirement.description}
          </p>
        </CardContent>
      </Card>

      {/* Source Quote */}
      {requirement.source_quote && (
        <Card>
          <CardHeader>
            <CardTitle>{t("sourceQuote")}</CardTitle>
          </CardHeader>
          <CardContent>
            <blockquote className="border-l-4 border-muted-foreground/30 pl-4 italic text-sm text-muted-foreground">
              {requirement.source_quote}
            </blockquote>
          </CardContent>
        </Card>
      )}

      {/* Related Questions */}
      <Card>
        <Collapsible open={questionsOpen} onOpenChange={setQuestionsOpen}>
          <CardHeader>
            <CollapsibleTrigger className="flex w-full items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <MessageCircle className="h-4 w-4" />
                {t("relatedQuestions")}
                {requirement.open_questions.length > 0 && (
                  <Badge variant="secondary">
                    {requirement.open_questions.length}
                  </Badge>
                )}
              </CardTitle>
              {questionsOpen ? (
                <ChevronDown className="h-4 w-4" />
              ) : (
                <ChevronRight className="h-4 w-4" />
              )}
            </CollapsibleTrigger>
          </CardHeader>
          <CollapsibleContent>
            <CardContent>
              {requirement.open_questions.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  {t("noQuestions")}
                </p>
              ) : (
                <div className="space-y-3">
                  {requirement.open_questions.map((q) => (
                    <div
                      key={q.id}
                      className="rounded-lg border p-3 space-y-1"
                    >
                      <p className="text-sm font-medium">{q.question}</p>
                      {q.answer ? (
                        <p className="text-sm text-muted-foreground">
                          <span className="font-medium">{t("answer")}:</span>{" "}
                          {q.answer}
                        </p>
                      ) : (
                        <Badge variant="outline" className="text-xs">
                          {t("unanswered")}
                        </Badge>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </CollapsibleContent>
        </Collapsible>
      </Card>

      {/* Metadata sidebar in card (for detail) */}
      <Card className="md:hidden">
        <CardHeader>
          <CardTitle>{t("detail")}</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="space-y-3 text-sm">
            <div className="flex justify-between">
              <dt className="text-muted-foreground">{t("status")}</dt>
              <dd>
                <StatusBadge status={requirement.status} />
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted-foreground">{t("priority")}</dt>
              <dd>
                <PriorityBadge priority={requirement.priority} />
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted-foreground">{t("category")}</dt>
              <dd>
                <Badge variant="secondary">{requirement.category}</Badge>
              </dd>
            </div>
          </dl>
        </CardContent>
      </Card>
    </div>
  );
}
