"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { Loader2, Pencil, Save } from "lucide-react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";

import {
  DOMAIN_LIST,
  updateControlPlaneAgent,
  type AgentDomain,
  type AgentInteractionMode,
  type AgentKind,
  type AgentMeta,
  type ControlPlaneAgentDefinition,
} from "@/entities/agent";
import { Button } from "@/shared/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/shared/ui/dialog";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/shared/ui/select";
import { Textarea } from "@/shared/ui/textarea";

interface AgentEditDialogProps {
  agent: ControlPlaneAgentDefinition;
  availableAgents: AgentMeta[];
  onUpdated?: (agent: ControlPlaneAgentDefinition) => void;
}

const AGENT_KIND_OPTIONS = [
  "organization_role",
  "business_runtime_agent",
  "capability_module",
  "integration_gateway",
  "system_worker",
] as const;

const INTERACTION_MODE_OPTIONS = ["direct", "routed", "internal", "none"] as const;
const ADAPTER_TYPES = ["builtin", "codex_local", "claude_local", "process", "http"] as const;

function lines(values: string[]): string {
  return values.join("\n");
}

function parseLines(value: string): string[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function configString(
  config: Record<string, unknown>,
  key: "base_url" | "path" | "command" | "model" | "cwd" | "prompt_template",
): string {
  const value = config[key];
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map(String).join(" ");
  return "";
}

function formFromAgent(agent: ControlPlaneAgentDefinition) {
  return {
    displayName: agent.display_name,
    agentKind: agent.agent_kind,
    interactionMode: agent.interaction_mode,
    role: agent.role,
    title: agent.title,
    domain: agent.domain as AgentDomain,
    reportsTo: agent.reports_to_agent_id ?? "none",
    adapterType: agent.adapter_type,
    baseUrl: configString(agent.adapter_config, "base_url"),
    path: configString(agent.adapter_config, "path"),
    command: configString(agent.adapter_config, "command"),
    model: configString(agent.adapter_config, "model"),
    cwd: configString(agent.adapter_config, "cwd"),
    promptTemplate: configString(agent.adapter_config, "prompt_template"),
    contextSources: lines(agent.context_sources),
    capabilities: lines(agent.capabilities),
    responsibilities: lines(agent.responsibilities),
    subscribedEvents: lines(agent.subscribed_events),
    publishedEvents: lines(agent.published_events),
  };
}

export function AgentEditDialog({ agent, availableAgents, onUpdated }: AgentEditDialogProps) {
  const t = useTranslations("agents");
  const td = useTranslations("agentDetail");
  const tc = useTranslations("common");
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState(() => formFromAgent(agent));

  useEffect(() => {
    if (!open) {
      setForm(formFromAgent(agent));
    }
  }, [agent, open]);

  const managerOptions = useMemo(
    () =>
      availableAgents
        .filter((item) => item.id !== agent.agent_id)
        .sort((a, b) => a.name.localeCompare(b.name)),
    [agent.agent_id, availableAgents],
  );

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);

    const adapterConfig = {
      ...(form.baseUrl.trim() ? { base_url: form.baseUrl.trim() } : {}),
      ...(form.path.trim() ? { path: form.path.trim() } : {}),
      ...(form.command.trim() ? { command: form.command.trim() } : {}),
      ...(form.model.trim() ? { model: form.model.trim() } : {}),
      ...(form.cwd.trim() ? { cwd: form.cwd.trim() } : {}),
      ...(form.promptTemplate.trim() ? { prompt_template: form.promptTemplate.trim() } : {}),
    };

    try {
      const updated = await updateControlPlaneAgent(agent.agent_id, {
        agent_id: agent.agent_id,
        display_name: form.displayName,
        agent_kind: form.agentKind,
        interaction_mode: form.interactionMode,
        role: form.role,
        title: form.title,
        domain: form.domain,
        reports_to_agent_id: form.reportsTo === "none" ? null : form.reportsTo,
        adapter_type: form.adapterType,
        adapter_config: adapterConfig,
        context_sources: parseLines(form.contextSources),
        capabilities: parseLines(form.capabilities),
        responsibilities: parseLines(form.responsibilities),
        subscribed_events: parseLines(form.subscribedEvents),
        published_events: parseLines(form.publishedEvents),
        permissions: agent.permissions,
        created_by: "frontend",
        metadata: agent.metadata,
      });
      toast.success(td("agentUpdateSuccess"));
      setOpen(false);
      onUpdated?.(updated);
    } catch {
      toast.error(tc("error"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button type="button" variant="outline">
          <Pencil />
          {td("editAgent")}
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{td("editAgent")}</DialogTitle>
          <DialogDescription>{td("editAgentDescription")}</DialogDescription>
        </DialogHeader>

        <form className="space-y-5" onSubmit={onSubmit}>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="edit-agent-name">{t("agentName")}</Label>
              <Input
                id="edit-agent-name"
                value={form.displayName}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    displayName: event.target.value,
                  }))
                }
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-agent-id">{t("agentId")}</Label>
              <Input id="edit-agent-id" value={agent.agent_id} disabled />
            </div>
            <div className="space-y-2">
              <Label>{t("agentKind")}</Label>
              <Select
                value={form.agentKind}
                onValueChange={(agentKind) =>
                  setForm((current) => ({
                    ...current,
                    agentKind: agentKind as AgentKind,
                  }))
                }
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {AGENT_KIND_OPTIONS.map((agentKind) => (
                    <SelectItem key={agentKind} value={agentKind}>
                      {t(`agentKinds.${agentKind}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>{t("interactionMode")}</Label>
              <Select
                value={form.interactionMode}
                onValueChange={(interactionMode) =>
                  setForm((current) => ({
                    ...current,
                    interactionMode: interactionMode as AgentInteractionMode,
                  }))
                }
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {INTERACTION_MODE_OPTIONS.map((interactionMode) => (
                    <SelectItem key={interactionMode} value={interactionMode}>
                      {t(`interactionModes.${interactionMode}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-muted-foreground text-xs">
                {t(`interactionModeDescriptions.${form.interactionMode}`)}
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-agent-role">{t("role")}</Label>
              <Input
                id="edit-agent-role"
                value={form.role}
                onChange={(event) =>
                  setForm((current) => ({ ...current, role: event.target.value }))
                }
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-agent-title">{t("titleField")}</Label>
              <Input
                id="edit-agent-title"
                value={form.title}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    title: event.target.value,
                  }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label>{t("domain")}</Label>
              <Select
                value={form.domain}
                onValueChange={(domain) =>
                  setForm((current) => ({
                    ...current,
                    domain: domain as AgentDomain,
                  }))
                }
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DOMAIN_LIST.map((domain) => (
                    <SelectItem key={domain.id} value={domain.id}>
                      {domain.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>{t("reportsTo")}</Label>
              <Select
                value={form.reportsTo}
                onValueChange={(reportsTo) => setForm((current) => ({ ...current, reportsTo }))}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">{t("noManager")}</SelectItem>
                  {managerOptions.map((manager) => (
                    <SelectItem key={manager.id} value={manager.id}>
                      {manager.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>{t("adapterType")}</Label>
              <Select
                value={form.adapterType}
                onValueChange={(adapterType) => setForm((current) => ({ ...current, adapterType }))}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ADAPTER_TYPES.map((adapterType) => (
                    <SelectItem key={adapterType} value={adapterType}>
                      {adapterType}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-agent-model">{t("model")}</Label>
              <Input
                id="edit-agent-model"
                value={form.model}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    model: event.target.value,
                  }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-agent-base-url">{t("baseUrl")}</Label>
              <Input
                id="edit-agent-base-url"
                value={form.baseUrl}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    baseUrl: event.target.value,
                  }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-agent-path">{t("requestPath")}</Label>
              <Input
                id="edit-agent-path"
                value={form.path}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    path: event.target.value,
                  }))
                }
              />
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="edit-agent-cwd">{t("workingDirectory")}</Label>
              <Input
                id="edit-agent-cwd"
                value={form.cwd}
                onChange={(event) =>
                  setForm((current) => ({ ...current, cwd: event.target.value }))
                }
              />
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="edit-agent-command">{t("command")}</Label>
              <Input
                id="edit-agent-command"
                value={form.command}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    command: event.target.value,
                  }))
                }
              />
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="edit-agent-context">{t("contextSources")}</Label>
              <Textarea
                id="edit-agent-context"
                value={form.contextSources}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    contextSources: event.target.value,
                  }))
                }
                className="min-h-20 font-mono text-sm"
              />
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="edit-agent-capabilities">{t("capabilities")}</Label>
              <Textarea
                id="edit-agent-capabilities"
                value={form.capabilities}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    capabilities: event.target.value,
                  }))
                }
                className="min-h-24"
              />
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="edit-agent-responsibilities">{t("responsibilities")}</Label>
              <Textarea
                id="edit-agent-responsibilities"
                value={form.responsibilities}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    responsibilities: event.target.value,
                  }))
                }
                className="min-h-24"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-agent-subscribed">{t("subscribedEvents")}</Label>
              <Textarea
                id="edit-agent-subscribed"
                value={form.subscribedEvents}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    subscribedEvents: event.target.value,
                  }))
                }
                className="min-h-24 font-mono text-sm"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-agent-published">{t("publishedEvents")}</Label>
              <Textarea
                id="edit-agent-published"
                value={form.publishedEvents}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    publishedEvents: event.target.value,
                  }))
                }
                className="min-h-24 font-mono text-sm"
              />
            </div>
          </div>

          <DialogFooter>
            <Button type="submit" disabled={submitting}>
              {submitting ? <Loader2 className="animate-spin" /> : <Save />}
              {submitting ? td("agentUpdating") : td("saveAgent")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
