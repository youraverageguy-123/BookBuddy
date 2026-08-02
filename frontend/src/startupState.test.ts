import { describe, expect, it, vi } from "vitest";
import { healthApi } from "./api/health";
import { migrateReaderState } from "./store/readerStore";

describe("startup state compatibility", () => {
  it("migrates custom mode without losing reader state", () => {
    const progress = { "Book::Reading::4": { percentage: 75 } };
    const migrated = migrateReaderState({
      theme: "dark",
      backendMode: "custom",
      customBackendUrl: "https://diagnostic.example",
      recentBooks: [{ book: "Book", session: "Reading", title: "Book", openedAt: 42 }],
      lastOpened: "Book::Reading",
      progress,
    });
    expect(migrated).not.toHaveProperty("backendMode");
    expect(migrated).toMatchObject({ theme: "dark", lastOpened: "Book::Reading", progress });
  });

  it("tests a custom backend directly without installing it as the app connection", async () => {
    const payload = {
      schema_version: "bookbuddy_health_v1",
      status: "ready",
      version: "test",
      storage: { library: "available" },
      capabilities: { chapter_analysis: false, dictionary: true, contextual_dictionary: true, pronunciation: true, recorded_audio: false, vision: false },
    };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(payload), { status: 200 }));
    await expect(healthApi.testCustom("https://diagnostic.example/")).resolves.toMatchObject({ version: "test" });
    expect(fetchMock).toHaveBeenCalledWith("https://diagnostic.example/health", { headers: { Accept: "application/json" } });
    fetchMock.mockRestore();
  });
});
