import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { AGENT_REGISTRY, useAgentPromptConfig, type AgentPromptConfig } from "@/entities/agent";
import { AgentConfig } from "./agent-config";

vi.mock("@/entities/agent", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/entities/agent")>(),
  useAgentPromptConfig: vi.fn(),
}));

it("keeps an unsaved prompt during refresh and resets to the latest saved prompt", async () => {
  const user = userEvent.setup();
  const saved: AgentPromptConfig = {
    company_id: "cmp_wisdoverse_cell",
    agent_id: "requirement-manager",
    system_prompt: "Original prompt",
    updated_by: null,
    metadata: {},
    created_at: null,
    updated_at: null,
  };
  const query = {
    data: saved,
    error: undefined,
    isLoading: false,
    isValidating: false,
    mutate: vi.fn(),
  };
  vi.mocked(useAgentPromptConfig).mockReturnValue(query);
  const meta = AGENT_REGISTRY["requirement-manager"];
  const { rerender } = render(<AgentConfig agentMeta={meta} />);
  expect(screen.getByLabelText("systemPrompt")).toHaveValue("Original prompt");
  expect(screen.getByRole("button", { name: "promptSave" })).toBeDisabled();

  await user.clear(screen.getByLabelText("systemPrompt"));
  await user.type(screen.getByLabelText("systemPrompt"), "Unsaved prompt");
  vi.mocked(useAgentPromptConfig).mockReturnValue({
    ...query,
    data: { ...saved, system_prompt: "Updated prompt" },
  });
  rerender(<AgentConfig agentMeta={meta} />);
  expect(screen.getByLabelText("systemPrompt")).toHaveValue("Unsaved prompt");

  await user.click(screen.getByRole("button", { name: "promptReset" }));
  expect(screen.getByLabelText("systemPrompt")).toHaveValue("Updated prompt");
  expect(screen.getByRole("button", { name: "promptSave" })).toBeDisabled();
});
