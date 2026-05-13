"use client";

import { FormEvent, useEffect, useMemo, useState, type ReactNode } from "react";
import { Loader2, Pencil, Save, Settings2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";

import {
  AGENT_ROLE_OPTIONS,
  DOMAIN_LIST,
  getAgentRoleOption,
  updateControlPlaneAgent,
  type AgentDomain,
  type AgentInteractionMode,
  type AgentKind,
  type AgentMeta,
  type ControlPlaneAgentDefinition,
} from "@/entities/agent";
import { Button } from "@/shared/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/shared/ui/collapsible";
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
const CUSTOM_ROLE_VALUE = "__custom_role__";
const ROLE_OPTION_IDS: ReadonlySet<string> = new Set(AGENT_ROLE_OPTIONS.map((option) => option.id));

function FormSection({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-lg border border-zinc-200/80 p-4 dark:border-white/10">
      <div className="space-y-1">
        <h3 className="text-sm font-semibold">{title}</h3>
        {description && <p className="text-muted-foreground text-xs leading-5">{description}</p>}
      </div>
      <div className="mt-4 grid gap-4 md:grid-cols-2">{children}</div>
    </section>
  );
}

function FieldNote({ children }: { children: ReactNode }) {
  return <p className="text-muted-foreground text-xs leading-5">{children}</p>;
}

function lines(values: string[]): string {
  return values.join("\n");
}

function parseLines(value: string): string[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function roleSelectValue(role: string): string {
  return ROLE_OPTION_IDS.has(role) ? role : CUSTOM_ROLE_VALUE;
}

function shouldUseSuggestedTitle(currentTitle: string, currentRole: string) {
  const currentRoleOption = getAgentRoleOption(currentRole);
  return !currentTitle.trim() || currentTitle === currentRoleOption?.title;
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
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [form, setForm] = useState(() => formFromAgent(agent));

  useEffect(() => {
    if (!open) {
      setForm(formFromAgent(agent));
      setAdvancedOpen(false);
    }
  }, [agent, open]);

  const managerOptions = useMemo(
    () =>
      availableAgents
        .filter((item) => item.id !== agent.agent_id)
        .sort((a, b) => a.name.localeCompare(b.name)),
    [agent.agent_id, availableAgents],
  );
  const selectedRoleValue = roleSelectValue(form.role);
  const canSubmit = Boolean(form.displayName.trim() && form.role.trim());

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
          <FormSection title={t("operatorBasics")} description={t("operatorBasicsDescription")}>
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
              <Label>{t("role")}</Label>
              <Select
                value={selectedRoleValue}
                onValueChange={(role) => {
                  if (role === CUSTOM_ROLE_VALUE) {
                    setForm((current) => ({ ...current, role: "" }));
                    return;
                  }
                  const roleOption = getAgentRoleOption(role);
                  setForm((current) => ({
                    ...current,
                    role,
                    title:
                      roleOption && shouldUseSuggestedTitle(current.title, current.role)
                        ? roleOption.title
                        : current.title,
                    domain: roleOption?.domain ?? current.domain,
                  }));
                }}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {AGENT_ROLE_OPTIONS.map((role) => (
                    <SelectItem key={role.id} value={role.id}>
                      {t(`agentRoles.${role.id}`)}
                    </SelectItem>
                  ))}
                  <SelectItem value={CUSTOM_ROLE_VALUE}>{t("customRole")}</SelectItem>
                </SelectContent>
              </Select>
              {selectedRoleValue === CUSTOM_ROLE_VALUE && (
                <div className="space-y-2">
                  <Label htmlFor="edit-agent-role">{t("customRoleValue")}</Label>
                  <Input
                    id="edit-agent-role"
                    value={form.role}
                    onChange={(event) =>
                      setForm((current) => ({ ...current, role: event.target.value }))
                    }
                    placeholder={t("customRoleValuePlaceholder")}
                    required
                  />
                </div>
              )}
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
            <div className="space-y-2 md:col-span-2">
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
                placeholder={t("capabilitiesPlaceholder")}
              />
              <FieldNote>{t("onePerLine")}</FieldNote>
            </div>
            <div className="space-y-2">
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
                placeholder={t("responsibilitiesPlaceholder")}
              />
              <FieldNote>{t("onePerLine")}</FieldNote>
            </div>
          </FormSection>

          <Collapsible open={advancedOpen} onOpenChange={setAdvancedOpen}>
            <section className="rounded-lg border border-zinc-200/80 p-4 dark:border-white/10">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="space-y-1">
                  <h3 className="text-sm font-semibold">{t("advancedSettings")}</h3>
                  <p className="text-muted-foreground text-xs leading-5">
                    {t("advancedSettingsDescription")}
                  </p>
                </div>
                <CollapsibleTrigger asChild>
                  <Button type="button" variant="outline" size="sm">
                    <Settings2 className="size-4" />
                    {advancedOpen ? t("hideAdvanced") : t("showAdvanced")}
                  </Button>
                </CollapsibleTrigger>
              </div>
              <CollapsibleContent>
                <div className="mt-4 grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="edit-agent-id">{t("agentId")}</Label>
                    <Input id="edit-agent-id" value={agent.agent_id} disabled />
                    <FieldNote>{t("agentIdHelp")}</FieldNote>
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
                    <FieldNote>
                      {t(`interactionModeDescriptions.${form.interactionMode}`)}
                    </FieldNote>
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
                  <div className="space-y-2">
                    <Label htmlFor="edit-agent-cwd">{t("workingDirectory")}</Label>
                    <Input
                      id="edit-agent-cwd"
                      value={form.cwd}
                      onChange={(event) =>
                        setForm((current) => ({
                          ...current,
                          cwd: event.target.value,
                        }))
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
                  <div className="space-y-2">
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
                      className="min-h-24 font-mono text-sm"
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
                  <div className="space-y-2">
                    <Label htmlFor="edit-agent-prompt-template">{t("promptTemplate")}</Label>
                    <Textarea
                      id="edit-agent-prompt-template"
                      value={form.promptTemplate}
                      onChange={(event) =>
                        setForm((current) => ({
                          ...current,
                          promptTemplate: event.target.value,
                        }))
                      }
                      className="min-h-24 font-mono text-sm"
                    />
                  </div>
                </div>
              </CollapsibleContent>
            </section>
          </Collapsible>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              {tc("cancel")}
            </Button>
            <Button type="submit" disabled={submitting || !canSubmit}>
              {submitting ? <Loader2 className="animate-spin" /> : <Save />}
              {submitting ? td("agentUpdating") : td("saveAgent")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
