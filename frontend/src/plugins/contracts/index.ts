export type SelectionActionId = "dictionary" | "story" | "character" | "copy" | "highlight" | "underline" | "note" | "search" | "translate";
export interface SelectionAction { id: SelectionActionId; label: string; order: number; capability?: string; }
export interface PluginPanel { id: string; label: string; route?: string; }
export interface ReaderPluginManifest {
  id: string; version: string; apiVersion: "reader-plugin-v1"; capabilities: string[];
  selectionActions: SelectionAction[]; panels: PluginPanel[]; backgroundTaskTypes: string[];
  requiredBackendCapabilities: string[];
}
export interface PluginAvailability { enabled: boolean; reason?: string; }
