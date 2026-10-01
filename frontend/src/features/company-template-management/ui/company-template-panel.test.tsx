import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ exportCompanyTemplate: vi.fn(), importCompanyTemplate: vi.fn() }));
vi.mock("../api/company-templates", () => api);
import { CompanyTemplatePanel } from "./company-template-panel";

const template = {
  schema_version: "1.0", company: { name: "Portable", mission: "Review" },
  goals: [], roles: [{ role_id: "editor", requested_permissions: ["write"] }], playbooks: [],
};

describe("CompanyTemplatePanel", () => {
  beforeEach(() => { api.importCompanyTemplate.mockReset().mockResolvedValue({ company_id: "new-company", goal_ids: {}, role_ids: {} }); });

  it("requires permissions review and makes imported paused-role behavior clear", async () => {
    render(<CompanyTemplatePanel companyId="source" />);
    const importButton = screen.getByRole("button", { name: "import" });
    expect(importButton).toBeDisabled();
    expect(screen.getByText("pausedRolesWarning")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("importJson"), { target: { value: JSON.stringify(template) } });
    expect(importButton).toBeDisabled();
    fireEvent.click(screen.getByLabelText("permissionsReview"));
    fireEvent.click(importButton);
    await waitFor(() => expect(api.importCompanyTemplate).toHaveBeenCalledWith(template, true));
    expect(await screen.findByRole("status")).toHaveTextContent("pausedRolesWarning");
  });

  it("renders invalid JSON and backend access-denial errors", async () => {
    render(<CompanyTemplatePanel companyId="source" />);
    fireEvent.change(screen.getByLabelText("importJson"), { target: { value: "{" } });
    fireEvent.click(screen.getByLabelText("permissionsReview"));
    fireEvent.click(screen.getByRole("button", { name: "import" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("JSON at position 1");
    api.importCompanyTemplate.mockRejectedValue(new Error("403 operator_scope_denied"));
    fireEvent.change(screen.getByLabelText("importJson"), { target: { value: JSON.stringify(template) } });
    fireEvent.click(screen.getByRole("button", { name: "import" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("403 operator_scope_denied");
  });
});
