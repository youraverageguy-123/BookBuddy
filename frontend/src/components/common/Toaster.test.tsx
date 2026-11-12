import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster } from "./Toaster";
import { toast, useToasts } from "./toast";

describe("toasts", () => {
  beforeEach(() => { vi.useFakeTimers(); useToasts.setState({ toasts: [] }); });
  afterEach(() => { cleanup(); vi.useRealTimers(); });

  it("announces messages, drops repeats, and clears them after a delay", () => {
    render(<Toaster/>);
    act(() => { toast.success("Bookmark added"); toast.success("Bookmark added"); toast.error("Import failed"); });
    expect(screen.getAllByText("Bookmark added")).toHaveLength(1);
    expect(screen.getByRole("alert").textContent).toContain("Import failed");
    act(() => { vi.advanceTimersByTime(4100); });
    expect(screen.queryByText("Bookmark added")).toBeNull();
    expect(screen.getByText("Import failed")).toBeTruthy();
    act(() => { vi.advanceTimersByTime(4000); });
    expect(screen.queryByText("Import failed")).toBeNull();
  });

  it("keeps only the newest few and can be dismissed by hand", () => {
    render(<Toaster/>);
    act(() => { for (const name of ["one", "two", "three", "four"]) toast.info(name); });
    expect(screen.queryByText("one")).toBeNull();
    expect(screen.getByText("four")).toBeTruthy();
    act(() => { screen.getAllByLabelText("Dismiss message")[0]?.click(); });
    expect(screen.queryByText("two")).toBeNull();
  });
});
