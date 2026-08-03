import { invoke } from "@tauri-apps/api/core";
import { save } from "@tauri-apps/plugin-dialog";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { readerStateApi } from "../api/readerState";
import { exportReadingTelemetry } from "./telemetryExport";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
vi.mock("@tauri-apps/plugin-dialog", () => ({ save: vi.fn() }));
vi.mock("../api/readerState", () => ({ readerStateApi: { exportStatistics: vi.fn() } }));

describe("reading telemetry export", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window, "__TAURI_INTERNALS__", { value: {}, configurable: true });
  });

  it("writes the backend export through the native protected export command and returns its path", async () => {
    vi.mocked(readerStateApi.exportStatistics).mockResolvedValue(new TextEncoder().encode('{"statistics":{}}').buffer);
    vi.mocked(invoke).mockResolvedValue("C:\\BookBuddy\\exports\\bookbuddy-reading-data.json");

    await expect(exportReadingTelemetry("profile-id")).resolves.toBe("C:\\BookBuddy\\exports\\bookbuddy-reading-data.json");
    expect(invoke).toHaveBeenCalledWith("save_text_export", {
      filename: "bookbuddy-reading-data.json",
      contents: '{"statistics":{}}',
    });
  });

  it("uses the Windows save dialog when the user chooses a location", async () => {
    vi.mocked(readerStateApi.exportStatistics).mockResolvedValue(new TextEncoder().encode('{"statistics":{}}').buffer);
    vi.mocked(save).mockResolvedValue("D:\\Exports\\reading.json");
    vi.mocked(invoke).mockResolvedValue("D:\\Exports\\reading.json");

    await expect(exportReadingTelemetry("profile-id", "choose")).resolves.toEqual({ status: "saved", path: "D:\\Exports\\reading.json" });
    expect(invoke).toHaveBeenCalledWith("save_text_export_to_path", { path: "D:\\Exports\\reading.json", contents: '{"statistics":{}}' });
  });

  it("does not write when the save dialog is cancelled", async () => {
    vi.mocked(readerStateApi.exportStatistics).mockResolvedValue(new ArrayBuffer(0));
    vi.mocked(save).mockResolvedValue(null);
    await expect(exportReadingTelemetry("profile-id", "choose")).resolves.toEqual({ status: "cancelled" });
    expect(invoke).not.toHaveBeenCalled();
  });
});
