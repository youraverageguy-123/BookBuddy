import { invoke } from "@tauri-apps/api/core";
import { save } from "@tauri-apps/plugin-dialog";
import { readerStateApi } from "../api/readerState";

const EXPORT_NAME = "bookbuddy-reading-data.json";
export type TelemetryExportDestination = "choose" | "default";
export type TelemetryExportResult = { status: "saved"; path: string } | { status: "cancelled" };

export function exportReadingTelemetry(userId: string): Promise<string>;
export function exportReadingTelemetry(userId: string, destination: TelemetryExportDestination): Promise<TelemetryExportResult>;
export async function exportReadingTelemetry(userId: string, destination?: TelemetryExportDestination): Promise<string | TelemetryExportResult> {
  const buffer = await readerStateApi.exportStatistics(userId);
  if ("__TAURI_INTERNALS__" in window) {
    const contents = new TextDecoder().decode(buffer);
    if (destination === "choose") {
      const path = await save({
        title: "Export BookBuddy reading data",
        defaultPath: EXPORT_NAME,
        filters: [{ name: "JSON data", extensions: ["json"] }],
      });
      if (!path) return { status: "cancelled" };
      return { status: "saved", path: await invoke<string>("save_text_export_to_path", { path, contents }) };
    }
    const savedPath = await invoke<string>("save_text_export", { filename: EXPORT_NAME, contents });
    return destination === undefined ? savedPath : { status: "saved", path: savedPath };
  }

  const url = URL.createObjectURL(new Blob([buffer], { type: "application/json" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = EXPORT_NAME;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
  return destination === undefined ? EXPORT_NAME : { status: "saved", path: EXPORT_NAME };
}
