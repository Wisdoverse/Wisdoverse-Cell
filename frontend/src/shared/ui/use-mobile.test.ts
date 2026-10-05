import { act, renderHook } from "@testing-library/react";
import { createElement } from "react";
import { renderToString } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";
import { useIsMobile } from "./use-mobile";

afterEach(() => vi.unstubAllGlobals());

it("uses a server snapshot and tracks media changes until unmount", () => {
  const listeners = new Set<() => void>();
  const query = {
    matches: true,
    addEventListener: vi.fn((_event: string, listener: () => void) => listeners.add(listener)),
    removeEventListener: vi.fn((_event: string, listener: () => void) => listeners.delete(listener)),
  };
  const matchMedia = vi.fn(() => query);
  vi.stubGlobal("matchMedia", matchMedia);

  function Probe() {
    return useIsMobile() ? "mobile" : "desktop";
  }
  expect(renderToString(createElement(Probe))).toBe("desktop");
  expect(matchMedia).not.toHaveBeenCalled();

  const { result, unmount } = renderHook(useIsMobile);
  expect(result.current).toBe(true);
  expect(matchMedia).toHaveBeenCalledWith("(max-width: 767px)");
  act(() => {
    query.matches = false;
    listeners.forEach((listener) => listener());
  });
  expect(result.current).toBe(false);

  unmount();
  expect(listeners.size).toBe(0);
  expect(query.removeEventListener).toHaveBeenCalledWith("change", expect.any(Function));
});
