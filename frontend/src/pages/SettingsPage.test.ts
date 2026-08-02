import { describe, expect, it } from "vitest";
import settingsSource from "./SettingsPage.tsx?raw";
import storeSource from "../store/readerStore.ts?raw";

describe("main settings persistence", () => {
  it("applies changes immediately without a global save button", () => {
    expect(settingsSource).not.toContain("Save settings");
    expect(settingsSource).not.toContain("settings-save");
    expect(settingsSource).toContain("state.setAppearance(");
    expect(settingsSource).toContain("state.setLibraryPreferences(");
    expect(storeSource).toContain('invoke("portable_config_file", { filename })');
    expect(storeSource).toContain("await store.set(name, value)");
    expect(storeSource).toContain("await store.save()");
  });
});
