import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ColumnDef } from "@tanstack/react-table";
import { DataTable } from "@/shared/ui/data-table";

// next-intl is globally mocked – useTranslations("common") returns key lookup,
// so the empty state shows the key "noData".

interface TestRow {
  id: string;
  name: string;
  value: number;
}

const columns: ColumnDef<TestRow, unknown>[] = [
  { accessorKey: "name", header: "Name" },
  { accessorKey: "value", header: "Value" },
];

const sampleData: TestRow[] = [
  { id: "1", name: "Alpha", value: 10 },
  { id: "2", name: "Beta", value: 20 },
  { id: "3", name: "Gamma", value: 30 },
];

describe("DataTable", () => {
  it("renders column headers", () => {
    render(<DataTable columns={columns} data={sampleData} />);

    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("Value")).toBeInTheDocument();
  });

  it("renders data rows", () => {
    render(<DataTable columns={columns} data={sampleData} />);

    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("Beta")).toBeInTheDocument();
    expect(screen.getByText("Gamma")).toBeInTheDocument();
    expect(screen.getByText("10")).toBeInTheDocument();
    expect(screen.getByText("20")).toBeInTheDocument();
    expect(screen.getByText("30")).toBeInTheDocument();
  });

  it("shows empty state when data is empty", () => {
    render(<DataTable columns={columns} data={[]} />);

    // The mock translator returns the key itself
    expect(screen.getByText("noData")).toBeInTheDocument();
  });

  it("shows loading skeleton when isLoading is true", () => {
    const { container } = render(
      <DataTable columns={columns} data={[]} isLoading />,
    );

    // Loading state renders Skeleton divs (data-slot="skeleton")
    const skeletons = container.querySelectorAll('[data-slot="skeleton"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  describe("pagination", () => {
    it("shows pagination controls when total exceeds pageSize", () => {
      const onPageChange = vi.fn();
      render(
        <DataTable
          columns={columns}
          data={sampleData}
          page={1}
          pageSize={2}
          total={6}
          onPageChange={onPageChange}
        />,
      );

      // Should show page info
      expect(screen.getByText(/6 items/)).toBeInTheDocument();
      expect(screen.getByText(/page 1\/3/)).toBeInTheDocument();
    });

    it("calls onPageChange when next button is clicked", async () => {
      const user = userEvent.setup();
      const onPageChange = vi.fn();

      render(
        <DataTable
          columns={columns}
          data={sampleData}
          page={1}
          pageSize={2}
          total={6}
          onPageChange={onPageChange}
        />,
      );

      // Find the "next" button (the second button in the pagination controls)
      const buttons = screen.getAllByRole("button");
      const nextButton = buttons[buttons.length - 1];
      await user.click(nextButton);

      expect(onPageChange).toHaveBeenCalledWith(2);
    });

    it("disables the previous button on the first page", () => {
      render(
        <DataTable
          columns={columns}
          data={sampleData}
          page={1}
          pageSize={2}
          total={6}
          onPageChange={vi.fn()}
        />,
      );

      const buttons = screen.getAllByRole("button");
      const prevButton = buttons[buttons.length - 2];
      expect(prevButton).toBeDisabled();
    });

    it("does not show pagination when total fits in one page", () => {
      render(
        <DataTable
          columns={columns}
          data={sampleData}
          page={1}
          pageSize={20}
          total={3}
          onPageChange={vi.fn()}
        />,
      );

      expect(screen.queryByText(/items/)).not.toBeInTheDocument();
    });
  });

  it("calls onRowClick when a row is clicked", async () => {
    const user = userEvent.setup();
    const onRowClick = vi.fn();

    render(
      <DataTable
        columns={columns}
        data={sampleData}
        onRowClick={onRowClick}
      />,
    );

    await user.click(screen.getByText("Alpha"));
    expect(onRowClick).toHaveBeenCalledWith(sampleData[0]);
  });
});
