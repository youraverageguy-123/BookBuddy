import { fireEvent, render, screen } from "@testing-library/react";
import { Outlet } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import App from "./App";

vi.mock("./components/layout/AppShell", () => ({ AppShell: () => <Outlet /> }));
vi.mock("./pages/LibraryPage", () => ({
  default: ({ onReady }: { onReady?: () => void }) => <button onClick={onReady}>Library loaded</button>,
}));

describe("desktop startup route handoff", () => {
  it("forwards the ready callback to the Library route", () => {
    window.location.hash = "#/library";
    const onReady = vi.fn();
    render(<App onLibraryReady={onReady} />);

    fireEvent.click(screen.getByRole("button", { name: "Library loaded" }));

    expect(onReady).toHaveBeenCalledOnce();
  });
});
