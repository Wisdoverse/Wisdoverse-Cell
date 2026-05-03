"use client";

import type { ReactNode } from "react";
import { useTranslations } from "next-intl";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { AgentDomainBadge, type AgentMeta } from "@/entities/agent";

interface AgentConfigProps {
  agentMeta: AgentMeta;
}

export function AgentConfig({ agentMeta }: AgentConfigProps) {
  const t = useTranslations("agentDetail");

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
      </CardContent>
    </Card>
  );
}
