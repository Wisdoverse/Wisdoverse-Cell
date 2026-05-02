"use client";

import { useTranslations } from "next-intl";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { DomainBadge } from "@/components/shared/domain-badge";
import type { AgentMeta } from "@/lib/api/types";

interface AgentConfigProps {
  agentMeta: AgentMeta;
}

export function AgentConfig({ agentMeta }: AgentConfigProps) {
  const t = useTranslations("agentDetail");

  const configEntries: {
    label: string;
    value: React.ReactNode;
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
      value: <DomainBadge domain={agentMeta.domain} />,
    },
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
