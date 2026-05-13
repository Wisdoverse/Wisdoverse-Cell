import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it } from "vitest";

import { AgentCreateDialog } from "./agent-create-dialog";

beforeAll(() => {
  Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});
  Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture ?? (() => false);
  Element.prototype.releasePointerCapture = Element.prototype.releasePointerCapture ?? (() => {});
});

describe("AgentCreateDialog", () => {
  it("fills organization-role defaults from a role template", async () => {
    const user = userEvent.setup();

    render(<AgentCreateDialog availableAgents={[]} />);

    await user.click(screen.getByRole("button", { name: "createAgent" }));
    expect(screen.getByText("operatorBasics")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "showAdvanced" })).toBeInTheDocument();
    await user.click(screen.getAllByRole("combobox")[0]);
    await user.click(await screen.findByRole("option", { name: "CTO" }));
    await user.click(screen.getByRole("button", { name: "showAdvanced" }));

    expect(screen.getByLabelText("agentName")).toHaveValue("CTO");
    expect(screen.getByLabelText("agentId")).toHaveValue("cto");
    expect(screen.getByLabelText("titleField")).toHaveValue("Chief Technology Officer");
    expect(screen.getByLabelText("contextSources")).toHaveValue("control_plane");
  }, 15_000);
});
