import { fireEvent, render, screen } from "@testing-library/react";
import { openUrl } from "@tauri-apps/plugin-opener";
import { describe, expect, it, vi } from "vitest";
import { AIWalkthrough } from "./AIWalkthrough";

vi.mock("@tauri-apps/plugin-opener", () => ({ openUrl: vi.fn() }));

describe("AIWalkthrough", () => {
  it("renders visible guide content and three semantic official links", () => {
    render(<AIWalkthrough open onOpenChange={vi.fn()}/>);

    expect(screen.getByRole("dialog", { name: "How to enable optional AI" })).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(4);
    expect(screen.getByRole("link", { name: /Get a free API key/ })).toHaveAttribute("href", "https://aistudio.google.com/app/apikey");
    expect(screen.getByRole("link", { name: /Official API key guide/ })).toHaveAttribute("href", "https://ai.google.dev/gemini-api/docs/api-key");
    expect(screen.getByRole("link", { name: /Gemini documentation/ })).toHaveAttribute("href", "https://ai.google.dev/gemini-api/docs");
  });

  it("opens a clicked official link through the restricted Tauri opener", () => {
    Object.defineProperty(window, "__TAURI_INTERNALS__", { value: {}, configurable: true });
    render(<AIWalkthrough open onOpenChange={vi.fn()}/>);

    fireEvent.click(screen.getByRole("link", { name: /Get a free API key/ }));

    expect(vi.mocked(openUrl)).toHaveBeenCalledWith("https://aistudio.google.com/app/apikey");
    Reflect.deleteProperty(window, "__TAURI_INTERNALS__");
  });
});
