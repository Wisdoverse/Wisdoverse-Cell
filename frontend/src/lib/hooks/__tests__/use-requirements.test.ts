import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import type { RequirementListResponse, Requirement } from "@/lib/api/types";

// ---------------------------------------------------------------------------
// Mock the requirements API module -- the hooks delegate to these functions.
// vi.mock is hoisted above imports automatically by vitest.
// ---------------------------------------------------------------------------
vi.mock("@/lib/api/requirements", () => ({
  listRequirements: vi.fn(),
  getRequirement: vi.fn(),
}));

// Import the mocked module and the hooks (which depend on it)
import { listRequirements, getRequirement } from "@/lib/api/requirements";
import {
  useRequirement,
  useRequirements,
} from "@/entities/requirement/model/use-requirements";

const mockListRequirements = vi.mocked(listRequirements);
const mockGetRequirement = vi.mocked(getRequirement);

const fakeRequirement: Requirement = {
  id: "req-1",
  title: "Test requirement",
  description: "A test requirement",
  source_quote: null,
  status: "pending",
  priority: "high",
  category: "功能",
  source_meeting_ids: [],
  confirmed_by: null,
  confirmed_at: null,
  rejection_reason: null,
  open_questions: [],
  history: [],
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2025-01-01T00:00:00Z",
};

const fakeListResponse: RequirementListResponse = {
  total: 1,
  page: 1,
  page_size: 20,
  items: [fakeRequirement],
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useRequirements", () => {
  it("returns data from the API", async () => {
    mockListRequirements.mockResolvedValue(fakeListResponse);

    const { result } = renderHook(() => useRequirements());

    await waitFor(() => {
      expect(result.current.data).toEqual(fakeListResponse);
    });

    expect(result.current.isLoading).toBe(false);
    expect(mockListRequirements).toHaveBeenCalledWith({});
  });

  it("passes filters to the API", async () => {
    mockListRequirements.mockResolvedValue(fakeListResponse);

    const filters = { status: "confirmed" as const, page: 2 };
    const { result } = renderHook(() => useRequirements(filters));

    await waitFor(() => {
      expect(result.current.data).toBeDefined();
    });

    expect(mockListRequirements).toHaveBeenCalledWith(filters);
  });

  it("calls the API and delivers data asynchronously", async () => {
    // Use a unique filter to avoid SWR cache hits from previous tests
    const uniqueFilters = { status: "pending" as const, page: 99 };
    let resolvePromise!: (value: RequirementListResponse) => void;
    mockListRequirements.mockReturnValue(
      new Promise<RequirementListResponse>((resolve) => {
        resolvePromise = resolve;
      }),
    );

    const { result } = renderHook(() => useRequirements(uniqueFilters));

    // Wait for SWR to invoke the fetcher
    await waitFor(() => {
      expect(mockListRequirements).toHaveBeenCalledTimes(1);
    });

    // Resolve and verify data arrives
    resolvePromise(fakeListResponse);

    await waitFor(() => {
      expect(result.current.data).toEqual(fakeListResponse);
    });
  });
});

describe("useRequirement", () => {
  it("returns a single requirement", async () => {
    mockGetRequirement.mockResolvedValue(fakeRequirement);

    const { result } = renderHook(() => useRequirement("req-1"));

    await waitFor(() => {
      expect(result.current.data).toEqual(fakeRequirement);
    });

    expect(mockGetRequirement).toHaveBeenCalledWith("req-1");
  });

  it("does not fetch when id is null", () => {
    const { result } = renderHook(() => useRequirement(null));

    expect(result.current.data).toBeUndefined();
    expect(mockGetRequirement).not.toHaveBeenCalled();
  });
});
