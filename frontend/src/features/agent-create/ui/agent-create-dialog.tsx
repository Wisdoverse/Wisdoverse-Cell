"use client";

import { FormEvent, useMemo, useState } from "react";
import { Loader2, UserPlus } from "lucide-react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";

import {
  createControlPlaneAgent,
  DOMAIN_LIST,
  type AgentDomain,
  type AgentMeta,
} from "@/entities/agent";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

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
  "manager",
  "engineer",
  "researcher",
  "operator",
  "qa",
  "worker",
] as const;

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
    agentId: "",
    displayName: "",
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
    capabilities: "",
    responsibilities: "",
  });

  const sortedAgents = useMemo(
    () => [...availableAgents].sort((a, b) => a.name.localeCompare(b.name)),
    [availableAgents],
  );

  function resetForm() {
    setForm({
      agentId: "",
      displayName: "",
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
      capabilities: "",
      responsibilities: "",
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
        role: form.role,
        title: form.title,
        domain: form.domain,
        reports_to_agent_id:
          form.reportsTo === "none" ? null : form.reportsTo,
        adapter_type: form.adapterType,
        adapter_config: adapterConfig,
        capabilities: parseLines(form.capabilities),
        responsibilities: parseLines(form.responsibilities),
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
        </DialogHeader>

        <form className="space-y-5" onSubmit={onSubmit}>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="agent-name">{t("agentName")}</Label>
              <Input
                id="agent-name"
                value={form.displayName}
                onChange={(event) => {
                  const displayName = event.target.value;
                  setForm((current) => ({
                    ...current,
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
                    agentId: slugify(event.target.value),
                  }));
                }}
                required
              />
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
