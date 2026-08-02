import { beforeEach, describe, expect, it, vi } from "vitest";
import type { StartupEvent } from "./startupContracts";

const invoke = vi.fn().mockResolvedValue(undefined);
const listeners = new Map<string, (event: { payload: unknown }) => void>();

vi.mock("@tauri-apps/api/core", () => ({ invoke }));
vi.mock("@tauri-apps/api/event", () => ({
  listen: vi.fn(async (name: string, callback: (event: { payload: unknown }) => void) => {
    listeners.set(name, callback);
    return () => undefined;
  }),
}));

describe("native startup splash", () => {
  beforeEach(async () => {
    vi.resetModules();
    invoke.mockClear();
    listeners.clear();
    document.documentElement.innerHTML = `<head></head><body>
      <main><p id="startup-message"></p><div id="startup-progress"></div><p id="startup-detail" hidden></p>
      <div id="startup-actions" hidden><button id="startup-retry">Retry</button><button id="startup-exit">Exit</button></div></main>
    </body>`;
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => { callback(0); return 1; });
    vi.stubGlobal("matchMedia", () => ({ matches: true }));
    await import("./splash");
  });

  it("renders completed stages without manufacturing a percentage", () => {
    const payload: StartupEvent = { attempt: 1, stage: "restoringSession", message: "Restoring workspace...", completedStages: 3, totalStages: 6, kind: "progress", actions: [] };
    listeners.get("bookbuddy://startup-stage")?.({ payload });
    expect(document.querySelector("#startup-message")).toHaveTextContent("Restoring workspace...");
    expect(document.querySelectorAll(".is-complete")).toHaveLength(3);
    expect(document.body.textContent).not.toMatch(/\d+%/);
  });

  it("keeps failures on the splash and wires retry, exit, and transition acknowledgement", () => {
    const payload: StartupEvent = { attempt: 2, stage: "failed", message: "Unable to start BookBuddy engine.", completedStages: 0, totalStages: 6, kind: "failure", actions: ["retry", "exit"] };
    listeners.get("bookbuddy://startup-stage")?.({ payload });
    expect(document.querySelector("#startup-actions")).not.toHaveAttribute("hidden");
    document.querySelector<HTMLButtonElement>("#startup-retry")?.click();
    expect(invoke).toHaveBeenCalledWith("startup_retry");
    listeners.get("bookbuddy://begin-transition")?.({ payload: undefined });
    expect(document.body).toHaveClass("is-leaving");
    expect(invoke).toHaveBeenCalledWith("startup_splash_faded");
  });
});
