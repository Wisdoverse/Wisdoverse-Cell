"use client";

import { FormEvent, useMemo, useState } from "react";
import { Loader2, UserPlus } from "lucide-react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";

import {
  createControlPlaneAgent,
  DOMAIN_LIST,
  ORGANIZATION_ROLE_TEMPLATES,
  type AgentDomain,
  type AgentInteractionMode,
  type AgentKind,
  type AgentMeta,
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/ui/select";
import { Textarea } from "@/shared/ui/textarea";

interface AgentCreateDialogProps {
  availableAgents: AgentMeta[];
  onCreated?: () => void;
}

const ADAPTER_TYPES = [
  "builtin",
  "codex_local",
  "claude_local",
  "process",
  "http",
] as const;

const ROLE_OPTIONS = [
  "ceo",
  "cto",
  "cpo",
  "coo",
  "cfo",
  "cmo",
  "manager",
  "engineer",
  "researcher",
  "operator",
  "qa",
  "worker",
] as const;

const AGENT_KIND_OPTIONS = [
  "organization_role",
  "capability_module",
  "integration_gateway",
  "system_worker",
] as const;

const INTERACTION_MODE_OPTIONS = ["direct", "routed", "internal", "none"] as const;

const CONTEXT_SOURCE_OPTIONS = [
  "control_plane",
  "feishu",
  "openproject",
  "gitlab",
  "agentforge",
  "event_bus",
  "scratchpad",
] as const;

const CUSTOM_TEMPLATE_VALUE = "custom";

function defaultInteractionMode(agentKind: AgentKind): AgentInteractionMode {
  if (agentKind === "organization_role") return "routed";
  if (agentKind === "integration_gateway") return "direct";
  return "internal";
}

function slugify(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64);
}

function parseLines(value: string): string[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

export function AgentCreateDialog({
  availableAgents,
  onCreated,
}: AgentCreateDialogProps) {
  const t = useTranslations("agents");
  const tc = useTranslations("common");
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [agentIdTouched, setAgentIdTouched] = useState(false);
  const [form, setForm] = useState({
    roleTemplate: CUSTOM_TEMPLATE_VALUE,
    agentId: "",
    displayName: "",
    agentKind: "organization_role" as AgentKind,
    interactionMode: "routed" as AgentInteractionMode,
    role: "engineer",
    title: "",
    domain: "engineering" as AgentDomain,
    reportsTo: "none",
    adapterType: "http",
    baseUrl: "",
    path: "/agent/request",
    command: "",
    model: "",
    cwd: "",
    promptTemplate: "",
    contextSources: "control_plane",
    capabilities: "",
    responsibilities: "",
    subscribedEvents: "",
    publishedEvents: "",
  });

  const sortedAgents = useMemo(
    () => [...availableAgents].sort((a, b) => a.name.localeCompare(b.name)),
    [availableAgents],
  );

  function resetForm() {
    setForm({
      roleTemplate: CUSTOM_TEMPLATE_VALUE,
      agentId: "",
      displayName: "",
      agentKind: "organization_role",
      interactionMode: "routed",
      role: "engineer",
      title: "",
      domain: "engineering",
      reportsTo: "none",
      adapterType: "http",
      baseUrl: "",
      path: "/agent/request",
      command: "",
      model: "",
      cwd: "",
      promptTemplate: "",
      contextSources: "control_plane",
      capabilities: "",
      responsibilities: "",
      subscribedEvents: "",
      publishedEvents: "",
    });
    setAgentIdTouched(false);
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    const adapterConfig = {
      ...(form.baseUrl.trim() ? { base_url: form.baseUrl.trim() } : {}),
      ...(form.path.trim() ? { path: form.path.trim() } : {}),
      ...(form.command.trim() ? { command: form.command.trim() } : {}),
      ...(form.model.trim() ? { model: form.model.trim() } : {}),
      ...(form.cwd.trim() ? { cwd: form.cwd.trim() } : {}),
      ...(form.promptTemplate.trim()
        ? { prompt_template: form.promptTemplate.trim() }
        : {}),
    };

    try {
      await createControlPlaneAgent({
        agent_id: form.agentId,
        display_name: form.displayName,
        agent_kind: form.agentKind,
        interaction_mode: form.interactionMode,
        role: form.role,
        title: form.title,
        domain: form.domain,
        reports_to_agent_id:
          form.reportsTo === "none" ? null : form.reportsTo,
        adapter_type: form.adapterType,
        adapter_config: adapterConfig,
        context_sources: parseLines(form.contextSources),
        capabilities: parseLines(form.capabilities),
        responsibilities: parseLines(form.responsibilities),
        subscribed_events: parseLines(form.subscribedEvents),
        published_events: parseLines(form.publishedEvents),
        created_by: "frontend",
      });
      toast.success(t("createSuccess"));
      setOpen(false);
      resetForm();
      onCreated?.();
    } catch {
      toast.error(tc("error"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <UserPlus />
          {t("createAgent")}
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{t("createAgent")}</DialogTitle>
          <DialogDescription>{t("createAgentDescription")}</DialogDescription>
        </DialogHeader>

        <form className="space-y-5" onSubmit={onSubmit}>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2 md:col-span-2">
              <Label>{t("roleTemplate")}</Label>
              <Select
                value={form.roleTemplate}
                onValueChange={(roleTemplate) => {
                  const template = ORGANIZATION_ROLE_TEMPLATES.find(
                    (item) => item.agentId === roleTemplate,
                  );
                  if (!template) {
                    setForm((current) => ({
                      ...current,
                      roleTemplate: CUSTOM_TEMPLATE_VALUE,
                    }));
                    return;
                  }
                  setForm((current) => ({
                    ...current,
                    roleTemplate,
                    agentId: template.agentId,
                    displayName: template.displayName,
                    agentKind: template.agentKind,
                    interactionMode: template.interactionMode,
                    role: template.role,
                    title: template.title,
                    domain: template.domain,
                    reportsTo: "none",
                    adapterType: current.adapterType || "http",
                    contextSources: "control_plane",
                    subscribedEvents: "",
                    publishedEvents: "",
                  }));
                  setAgentIdTouched(true);
                }}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={CUSTOM_TEMPLATE_VALUE}>
                    {t("customRole")}
                  </SelectItem>
                  {ORGANIZATION_ROLE_TEMPLATES.map((template) => (
                    <SelectItem key={template.agentId} value={template.agentId}>
                      {template.displayName}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="agent-name">{t("agentName")}</Label>
              <Input
                id="agent-name"
                value={form.displayName}
                onChange={(event) => {
                  const displayName = event.target.value;
                  setForm((current) => ({
                    ...current,
                    roleTemplate: CUSTOM_TEMPLATE_VALUE,
                    displayName,
                    agentId: agentIdTouched
                      ? current.agentId
                      : slugify(displayName),
                  }));
                }}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="agent-id">{t("agentId")}</Label>
              <Input
                id="agent-id"
                value={form.agentId}
                pattern="^[a-z0-9][a-z0-9._-]*$"
                onChange={(event) => {
                  setAgentIdTouched(true);
                  setForm((current) => ({
                    ...current,
                    roleTemplate: CUSTOM_TEMPLATE_VALUE,
                    agentId: slugify(event.target.value),
                  }));
                }}
                required
              />
            </div>
            <div className="space-y-2">
              <Label>{t("agentKind")}</Label>
              <Select
                value={form.agentKind}
                onValueChange={(agentKind) => {
                  const nextKind = agentKind as AgentKind;
                  setForm((current) => ({
                    ...current,
                    agentKind: nextKind,
                    interactionMode: defaultInteractionMode(nextKind),
                  }));
                }}
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
            </div>
            <div className="space-y-2">
              <Label>{t("role")}</Label>
              <Select
                value={form.role}
                onValueChange={(role) =>
                  setForm((current) => ({ ...current, role }))
                }
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ROLE_OPTIONS.map((role) => (
                    <SelectItem key={role} value={role}>
                      {role}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="agent-title">{t("titleField")}</Label>
              <Input
                id="agent-title"
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
                onValueChange={(reportsTo) =>
                  setForm((current) => ({ ...current, reportsTo }))
                }
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">{t("noManager")}</SelectItem>
                  {sortedAgents.map((agent) => (
                    <SelectItem key={agent.id} value={agent.id}>
                      {agent.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>{t("adapterType")}</Label>
              <Select
                value={form.adapterType}
                onValueChange={(adapterType) =>
                  setForm((current) => ({ ...current, adapterType }))
                }
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
              <Label htmlFor="agent-model">{t("model")}</Label>
              <Input
                id="agent-model"
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
              <Label htmlFor="agent-base-url">{t("baseUrl")}</Label>
              <Input
                id="agent-base-url"
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
              <Label htmlFor="agent-path">{t("requestPath")}</Label>
              <Input
                id="agent-path"
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
              <Label htmlFor="agent-cwd">{t("workingDirectory")}</Label>
              <Input
                id="agent-cwd"
                value={form.cwd}
                onChange={(event) =>
                  setForm((current) => ({ ...current, cwd: event.target.value }))
                }
              />
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="agent-command">{t("command")}</Label>
              <Input
                id="agent-command"
                value={form.command}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    command: event.target.value,
                  }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="agent-context-sources">
                {t("contextSources")}
              </Label>
              <Textarea
                id="agent-context-sources"
                rows={4}
                value={form.contextSources}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    contextSources: event.target.value,
                  }))
                }
                placeholder={CONTEXT_SOURCE_OPTIONS.join("\n")}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="agent-capabilities">{t("capabilities")}</Label>
              <Textarea
                id="agent-capabilities"
                rows={4}
                value={form.capabilities}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    capabilities: event.target.value,
                  }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="agent-responsibilities">
                {t("responsibilities")}
              </Label>
              <Textarea
                id="agent-responsibilities"
                rows={4}
                value={form.responsibilities}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    responsibilities: event.target.value,
                  }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="agent-subscribed-events">
                {t("subscribedEvents")}
              </Label>
              <Textarea
                id="agent-subscribed-events"
                rows={4}
                value={form.subscribedEvents}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    subscribedEvents: event.target.value,
                  }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="agent-published-events">
                {t("publishedEvents")}
              </Label>
              <Textarea
                id="agent-published-events"
                rows={4}
                value={form.publishedEvents}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    publishedEvents: event.target.value,
                  }))
                }
              />
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="agent-prompt-template">{t("promptTemplate")}</Label>
              <Textarea
                id="agent-prompt-template"
                rows={4}
                value={form.promptTemplate}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    promptTemplate: event.target.value,
                  }))
                }
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
            >
              {tc("cancel")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting && <Loader2 className="animate-spin" />}
              {tc("save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
