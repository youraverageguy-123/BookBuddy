import { describe, expect, it } from "vitest";
import { startupDestinationHash } from "./startupDestination";

describe("startup destination", () => {
  it("always lands native startup on Home after state restoration", () => {
    const books = [{ session_key: "Book::Reading", last_opened_at: 42 }];
    expect(startupDestinationHash(true, "#/reader/Old/Session", "resume", books)).toBe("#/");
    expect(startupDestinationHash(true, "", "library", books)).toBe("#/");
  });

  it("retains browser-only destination preferences", () => {
    const books = [{ session_key: "Book::Reading", last_opened_at: 42 }];
    expect(startupDestinationHash(false, "", "resume", books)).toBe("#/reader/Book/Reading");
    expect(startupDestinationHash(false, "#/settings", "library", books)).toBeNull();
  });
});
