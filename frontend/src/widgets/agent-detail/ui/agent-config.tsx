"use client";

import { useEffect, useState, type ReactNode } from "react";
import { Loader2, RotateCcw, Save } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { toast } from "sonner";
import {
  AGENT_REGISTRY,
  AgentDomainBadge,
  updateAgentPromptConfig,
  useAgentPromptConfig,
  type AgentMeta,
  type AgentTabId,
  type ApprovalType,
} from "@/entities/agent";
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";
import { Label } from "@/shared/ui/label";
import { Textarea } from "@/shared/ui/textarea";

const MAX_PROMPT_LENGTH = 50_000;
const EMPTY_VALUE = "--";

const TAB_LABEL_KEYS: Record<AgentTabId, string> = {
  overview: "tabLabels.overview",
  tasks: "tabLabels.tasks",
  events: "tabLabels.events",
  connections: "tabLabels.connections",
  config: "tabLabels.config",
  logs: "tabLabels.logs",
};

const APPROVAL_TYPE_LABEL_KEYS: Record<ApprovalType, string> = {
  finance: "approvalTypeLabels.finance",
  legal: "approvalTypeLabels.legal",
  technical: "approvalTypeLabels.technical",
  customer: "approvalTypeLabels.customer",
};

const CONTEXT_SOURCE_LABEL_KEYS: Record<string, string> = {
  agentforge: "contextSourceLabels.agentforge",
  control_plane: "contextSourceLabels.controlPlane",
  event_bus: "contextSourceLabels.eventBus",
  feishu: "contextSourceLabels.feishu",
  gitlab: "contextSourceLabels.gitlab",
  manual_upload: "contextSourceLabels.manualUpload",
  openproject: "contextSourceLabels.openProject",
  scratchpad: "contextSourceLabels.scratchpad",
  traces: "contextSourceLabels.traces",
  wecom: "contextSourceLabels.wecom",
};

const ADAPTER_TYPE_LABEL_KEYS: Record<string, string> = {
  builtin: "adapterTypeLabels.builtin",
  http: "adapterTypeLabels.http",
  external_http: "adapterTypeLabels.http",
  openai_assistant: "adapterTypeLabels.openaiAssistant",
};

const WIDGET_LABEL_KEYS: Record<string, string> = {
  "rm-requirements": "widgetLabels.requirements",
  "rm-ingest": "widgetLabels.ingest",
  "rm-questions": "widgetLabels.questions",
};

const AGENT_ROLE_LABEL_KEYS: Record<string, string> = {
  "requirement-agent": "agentRoles.requirement-agent",
  "project-management-agent": "agentRoles.project-management-agent",
  "quality-agent": "agentRoles.quality-agent",
  "development-agent": "agentRoles.development-agent",
  "chat-agent": "agentRoles.chat-agent",
  orchestrator: "agentRoles.orchestrator",
  "sync-capability": "agentRoles.sync-capability",
  "analysis-capability": "agentRoles.analysis-capability",
  "evolution-capability": "agentRoles.evolution-capability",
  "channel-gateway": "agentRoles.channel-gateway",
};

type TranslationFn = (key: string) => string;

function humanizeIdentifier(value: string): string {
  return value
    .replace(/[_-]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function translateKnownValue(
  value: string,
  labelKeys: Record<string, string>,
  t: TranslationFn,
): string {
  const key = labelKeys[value];
  return key ? t(key) : humanizeIdentifier(value);
}

function formatAgentName(agentId: string): string {
  return AGENT_REGISTRY[agentId]?.name ?? humanizeIdentifier(agentId);
}

function formatUpdatedAt(value: string | null | undefined, locale: string): string | null {
  if (!value) return null;
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

interface AgentConfigProps {
  agentMeta: AgentMeta;
}

export function AgentConfig({ agentMeta }: AgentConfigProps) {
  const t = useTranslations("agentDetail");
  const ta = useTranslations("agents");
  const locale = useLocale();
  const promptQuery = useAgentPromptConfig(agentMeta.id);
  const [draftPrompt, setDraftPrompt] = useState("");
  const [savingPrompt, setSavingPrompt] = useState(false);
  const savedPrompt = promptQuery.data?.system_prompt ?? "";
  const isPromptDirty = draftPrompt !== savedPrompt;
  const isPromptTooLong = draftPrompt.length > MAX_PROMPT_LENGTH;
  const updatedAt = formatUpdatedAt(promptQuery.data?.updated_at, locale);

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

  const operatorEntries: {
    label: string;
    value: ReactNode;
  }[] = [
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
                {ta(`agentKinds.${agentMeta.agentKind}`)}
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
                {ta(`interactionModes.${agentMeta.interactionMode}`)}
              </Badge>
            ),
          },
        ]
      : []),
    ...(agentMeta.role
      ? [
          {
            label: t("role"),
            value: translateKnownValue(agentMeta.role, AGENT_ROLE_LABEL_KEYS, ta),
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
                    {translateKnownValue(source, CONTEXT_SOURCE_LABEL_KEYS, t)}
                  </Badge>
                ))}
              </div>
            ),
          },
        ]
      : []),
    {
      label: t("approvalTypes"),
      value:
        agentMeta.approvalTypes && agentMeta.approvalTypes.length > 0 ? (
          <div className="flex flex-wrap gap-1">
            {agentMeta.approvalTypes.map((approvalType) => (
              <Badge key={approvalType} variant="secondary">
                {translateKnownValue(approvalType, APPROVAL_TYPE_LABEL_KEYS, t)}
              </Badge>
            ))}
          </div>
        ) : (
          <span className="text-muted-foreground">{EMPTY_VALUE}</span>
        ),
    },
    {
      label: t("upstream"),
      value:
        agentMeta.upstream.length > 0 ? (
          <div className="flex flex-wrap gap-1">
            {agentMeta.upstream.map((id) => (
              <Badge key={id} variant="outline">
                {formatAgentName(id)}
              </Badge>
            ))}
          </div>
        ) : (
          <span className="text-muted-foreground">{t("noConnections")}</span>
        ),
    },
    {
      label: t("downstream"),
      value:
        agentMeta.downstream.length > 0 ? (
          <div className="flex flex-wrap gap-1">
            {agentMeta.downstream.map((id) => (
              <Badge key={id} variant="outline">
                {formatAgentName(id)}
              </Badge>
            ))}
          </div>
        ) : (
          <span className="text-muted-foreground">{t("noConnections")}</span>
        ),
    },
  ];

  const advancedEntries: {
    label: string;
    value: ReactNode;
  }[] = [
    {
      label: t("agentId"),
      value: (
        <code className="bg-muted rounded px-1.5 py-0.5 font-mono text-xs">{agentMeta.id}</code>
      ),
    },
    ...(agentMeta.adapterType
      ? [
          {
            label: t("adapterType"),
            value: (
              <Badge variant="outline" className="rounded-md">
                {translateKnownValue(agentMeta.adapterType, ADAPTER_TYPE_LABEL_KEYS, t)}
              </Badge>
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
              {t(TAB_LABEL_KEYS[tab])}
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
                {translateKnownValue(w, WIDGET_LABEL_KEYS, t)}
              </Badge>
            ))}
          </div>
        ) : (
          <span className="text-muted-foreground">{EMPTY_VALUE}</span>
        ),
    },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("config")}</CardTitle>
        <p className="text-muted-foreground text-sm">{t("configDescription")}</p>
      </CardHeader>
      <CardContent className="space-y-6">
        <dl className="space-y-4">
          {operatorEntries.map((entry) => (
            <div
              key={entry.label}
              className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between"
            >
              <dt className="text-muted-foreground shrink-0 text-sm font-medium sm:w-40">
                {entry.label}
              </dt>
              <dd className="text-sm">{entry.value}</dd>
            </div>
          ))}
        </dl>
        <details className="bg-muted/20 rounded-lg border p-4">
          <summary className="cursor-pointer text-sm font-medium">
            {t("advancedRuntimeDetails")}
          </summary>
          <p className="text-muted-foreground mt-2 text-xs">
            {t("advancedRuntimeDetailsDescription")}
          </p>
          <dl className="mt-4 space-y-4">
            {advancedEntries.map((entry) => (
              <div
                key={entry.label}
                className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between"
              >
                <dt className="text-muted-foreground shrink-0 text-sm font-medium sm:w-40">
                  {entry.label}
                </dt>
                <dd className="text-sm">{entry.value}</dd>
              </div>
            ))}
          </dl>
        </details>
        <div className="space-y-3 border-t pt-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div className="space-y-1">
              <Label htmlFor={`agent-system-prompt-${agentMeta.id}`}>{t("systemPrompt")}</Label>
              <p className="text-muted-foreground text-xs">{t("systemPromptDescription")}</p>
              <div className="text-muted-foreground text-xs">
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
                  !isPromptDirty || isPromptTooLong || savingPrompt || promptQuery.isLoading
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
