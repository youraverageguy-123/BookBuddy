import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FullscreenControls } from "./FullscreenControls";

describe("fullscreen dwell controls", () => {
  afterEach(() => { cleanup(); vi.useRealTimers(); });
  it("requires an uninterrupted one-second top-edge dwell", () => {
    vi.useFakeTimers(); const reveal = vi.fn();
    const { rerender } = render(<FullscreenControls fullscreen revealed={false} onRevealedChange={reveal} onHome={vi.fn()} onExit={vi.fn()} onMinimize={vi.fn()} onClose={vi.fn()}/>);
    const zone = screen.getByTestId("fullscreen-activation-zone");
    fireEvent.pointerEnter(zone); vi.advanceTimersByTime(999); expect(reveal).not.toHaveBeenCalled();
    fireEvent.pointerLeave(zone); vi.advanceTimersByTime(2); expect(reveal).not.toHaveBeenCalled();
    fireEvent.pointerEnter(zone); vi.advanceTimersByTime(1000); expect(reveal).toHaveBeenCalledWith(true);
    rerender(<FullscreenControls fullscreen revealed onRevealedChange={reveal} onHome={vi.fn()} onExit={vi.fn()} onMinimize={vi.fn()} onClose={vi.fn()}/>);
    expect(screen.getByRole("button", { name: "Go to Home" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Exit fullscreen" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Minimize window" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close window" })).toBeInTheDocument();
  });

  it("hides shortly after leaving the revealed toolbar", () => {
    vi.useFakeTimers(); const reveal = vi.fn();
    render(<FullscreenControls fullscreen revealed onRevealedChange={reveal} onHome={vi.fn()} onExit={vi.fn()} onMinimize={vi.fn()} onClose={vi.fn()}/>);
    fireEvent.pointerLeave(screen.getByRole("toolbar")); vi.advanceTimersByTime(449); expect(reveal).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1); expect(reveal).toHaveBeenCalledWith(false);
  });
});
