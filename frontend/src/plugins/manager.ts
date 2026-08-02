import { builtinPlugins } from "./builtins";
import type { ReaderPluginManifest, SelectionAction } from "./contracts";

export class ReaderPluginManager {
  private readonly plugins = new Map<string, ReaderPluginManifest>();
  constructor(manifests: ReaderPluginManifest[] = builtinPlugins) { for (const manifest of manifests) this.register(manifest); }
  register(manifest: ReaderPluginManifest): void {
    if (manifest.apiVersion !== "reader-plugin-v1" || this.plugins.has(manifest.id)) throw new Error(`Invalid or duplicate reader plugin: ${manifest.id}`);
    this.plugins.set(manifest.id, Object.freeze({ ...manifest, selectionActions: [...manifest.selectionActions], panels: [...manifest.panels] }));
  }
  manifests(): ReaderPluginManifest[] { return [...this.plugins.values()]; }
  selectionActions(capabilities: Record<string, boolean> = {}): Array<SelectionAction & { enabled: boolean }> {
    return this.manifests().flatMap((plugin) => plugin.selectionActions).sort((a,b) => a.order-b.order).map((action) => ({ ...action, enabled: !action.capability || Boolean(capabilities[action.capability]) }));
  }
}
export const readerPluginManager = new ReaderPluginManager();
