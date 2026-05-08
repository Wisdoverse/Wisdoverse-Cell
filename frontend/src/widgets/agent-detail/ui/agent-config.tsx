"use client";

import { useEffect, useState, type ReactNode } from "react";
import { Loader2, RotateCcw, Save } from "lucide-react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";
import {
  AgentDomainBadge,
  updateAgentPromptConfig,
  useAgentPromptConfig,
  type AgentMeta,
} from "@/entities/agent";
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";
import { Label } from "@/shared/ui/label";
import { Textarea } from "@/shared/ui/textarea";

const MAX_PROMPT_LENGTH = 50_000;

interface AgentConfigProps {
  agentMeta: AgentMeta;
}

export function AgentConfig({ agentMeta }: AgentConfigProps) {
  const t = useTranslations("agentDetail");
  const promptQuery = useAgentPromptConfig(agentMeta.id);
  const [draftPrompt, setDraftPrompt] = useState("");
  const [savingPrompt, setSavingPrompt] = useState(false);
  const savedPrompt = promptQuery.data?.system_prompt ?? "";
  const isPromptDirty = draftPrompt !== savedPrompt;
  const isPromptTooLong = draftPrompt.length > MAX_PROMPT_LENGTH;
  const updatedAt = promptQuery.data?.updated_at
    ? new Date(promptQuery.data.updated_at).toLocaleString()
    : null;

  useEffect(() => {
    if (promptQuery.data) {
      setDraftPrompt(promptQuery.data.system_prompt);
    }
  }, [promptQuery.data]);

  async function handlePromptSave() {
    if (!isPromptDirty || isPromptTooLong) return;
    setSavingPrompt(true);
    try {
      const saved = await updateAgentPromptConfig(agentMeta.id, {
        system_prompt: draftPrompt,
        updated_by: "webui",
        metadata: { source: "agent_detail_config_tab" },
      });
      setDraftPrompt(saved.system_prompt);
      await promptQuery.mutate(saved, { revalidate: false });
      toast.success(t("promptSaveSuccess"));
    } catch {
      toast.error(t("promptSaveError"));
    } finally {
      setSavingPrompt(false);
    }
  }

  function handlePromptReset() {
    setDraftPrompt(savedPrompt);
  }

  const configEntries: {
    label: string;
    value: ReactNode;
  }[] = [
    {
      label: t("agentId"),
      value: (
        <code className="rounded bg-muted px-1.5 py-0.5 text-xs font-mono">
          {agentMeta.id}
        </code>
      ),
    },
    {
      label: t("domain"),
      value: <AgentDomainBadge domain={agentMeta.domain} />,
    },
    ...(agentMeta.agentKind
      ? [
          {
            label: t("agentKind"),
            value: (
              <Badge variant="outline" className="rounded-md">
                {agentMeta.agentKind}
              </Badge>
            ),
          },
        ]
      : []),
    ...(agentMeta.interactionMode
      ? [
          {
            label: t("interactionMode"),
            value: (
              <Badge variant="outline" className="rounded-md">
                {agentMeta.interactionMode}
              </Badge>
            ),
          },
        ]
      : []),
    ...(agentMeta.role
      ? [
          {
            label: t("role"),
            value: agentMeta.role,
          },
        ]
      : []),
    ...(agentMeta.title
      ? [
          {
            label: t("titleField"),
            value: agentMeta.title,
          },
        ]
      : []),
    ...(agentMeta.adapterType
      ? [
          {
            label: t("adapterType"),
            value: (
              <Badge variant="outline" className="rounded-md">
                {agentMeta.adapterType}
              </Badge>
            ),
          },
        ]
      : []),
    ...(agentMeta.capabilities && agentMeta.capabilities.length > 0
      ? [
          {
            label: t("capabilities"),
            value: (
              <div className="flex flex-wrap gap-1">
                {agentMeta.capabilities.map((capability) => (
                  <Badge key={capability} variant="secondary">
                    {capability}
                  </Badge>
                ))}
              </div>
            ),
          },
        ]
      : []),
    ...(agentMeta.contextSources && agentMeta.contextSources.length > 0
      ? [
          {
            label: t("contextSources"),
            value: (
              <div className="flex flex-wrap gap-1">
                {agentMeta.contextSources.map((source) => (
                  <Badge key={source} variant="secondary">
                    {source}
                  </Badge>
                ))}
              </div>
            ),
          },
        ]
      : []),
    ...(agentMeta.subscribedEvents && agentMeta.subscribedEvents.length > 0
      ? [
          {
            label: t("subscribedEvents"),
            value: (
              <div className="flex flex-wrap gap-1">
                {agentMeta.subscribedEvents.map((eventType) => (
                  <Badge key={eventType} variant="secondary">
                    {eventType}
                  </Badge>
                ))}
              </div>
            ),
          },
        ]
      : []),
    ...(agentMeta.publishedEvents && agentMeta.publishedEvents.length > 0
      ? [
          {
            label: t("publishedEvents"),
            value: (
              <div className="flex flex-wrap gap-1">
                {agentMeta.publishedEvents.map((eventType) => (
                  <Badge key={eventType} variant="secondary">
                    {eventType}
                  </Badge>
                ))}
              </div>
            ),
          },
        ]
      : []),
    {
      label: t("tabs"),
      value: (
        <div className="flex flex-wrap gap-1">
          {agentMeta.tabs.map((tab) => (
            <Badge key={tab} variant="secondary">
              {tab}
            </Badge>
          ))}
        </div>
      ),
    },
    {
      label: t("widgets"),
      value:
        agentMeta.customWidgets && agentMeta.customWidgets.length > 0 ? (
          <div className="flex flex-wrap gap-1">
            {agentMeta.customWidgets.map((w) => (
              <Badge key={w} variant="outline">
                {w}
              </Badge>
            ))}
          </div>
        ) : (
          <span className="text-muted-foreground">--</span>
        ),
    },
    {
      label: t("approvalTypes"),
      value:
        agentMeta.approvalTypes && agentMeta.approvalTypes.length > 0 ? (
          <div className="flex flex-wrap gap-1">
            {agentMeta.approvalTypes.map((a) => (
              <Badge key={a} variant="secondary" className="capitalize">
                {a}
              </Badge>
            ))}
          </div>
        ) : (
          <span className="text-muted-foreground">--</span>
        ),
    },
    {
      label: t("upstream"),
      value:
        agentMeta.upstream.length > 0 ? (
          <div className="flex flex-wrap gap-1">
            {agentMeta.upstream.map((id) => (
              <Badge key={id} variant="outline">
                {id}
              </Badge>
            ))}
          </div>
        ) : (
          <span className="text-muted-foreground">--</span>
        ),
    },
    {
      label: t("downstream"),
      value:
        agentMeta.downstream.length > 0 ? (
          <div className="flex flex-wrap gap-1">
            {agentMeta.downstream.map((id) => (
              <Badge key={id} variant="outline">
                {id}
              </Badge>
            ))}
          </div>
        ) : (
          <span className="text-muted-foreground">--</span>
        ),
    },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("config")}</CardTitle>
      </CardHeader>
      <CardContent>
        <dl className="space-y-4">
          {configEntries.map((entry) => (
            <div
              key={entry.label}
              className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-1"
            >
              <dt className="text-sm font-medium text-muted-foreground shrink-0 sm:w-40">
                {entry.label}
              </dt>
              <dd className="text-sm">{entry.value}</dd>
            </div>
          ))}
        </dl>
        <div className="mt-6 space-y-3 border-t pt-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div className="space-y-1">
              <Label htmlFor={`agent-system-prompt-${agentMeta.id}`}>
                {t("systemPrompt")}
              </Label>
              <div className="text-xs text-muted-foreground">
                {promptQuery.error
                  ? t("promptLoadError")
                  : updatedAt
                    ? `${t("promptUpdatedAt")} ${updatedAt}`
                    : t("promptNotConfigured")}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handlePromptReset}
                disabled={!isPromptDirty || savingPrompt}
              >
                <RotateCcw />
                {t("promptReset")}
              </Button>
              <Button
                type="button"
                size="sm"
                onClick={handlePromptSave}
                disabled={
                  !isPromptDirty ||
                  isPromptTooLong ||
                  savingPrompt ||
                  promptQuery.isLoading
                }
              >
                {savingPrompt ? <Loader2 className="animate-spin" /> : <Save />}
                {savingPrompt ? t("promptSaving") : t("promptSave")}
              </Button>
            </div>
          </div>
          <Textarea
            id={`agent-system-prompt-${agentMeta.id}`}
            value={draftPrompt}
            onChange={(event) => setDraftPrompt(event.target.value)}
            maxLength={MAX_PROMPT_LENGTH}
            disabled={promptQuery.isLoading || savingPrompt}
            className="min-h-72 resize-y font-mono text-sm leading-6"
          />
          <div
            className={`text-right text-xs ${
              isPromptTooLong ? "text-destructive" : "text-muted-foreground"
            }`}
          >
            {draftPrompt.length}/{MAX_PROMPT_LENGTH}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
