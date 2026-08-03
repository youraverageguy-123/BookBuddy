import { describe, expect, it } from "vitest";
import onboardingSource from "./AIOnboardingCard.tsx?raw";
import settingsSource from "./AISettingsPanel.tsx?raw";
import metadataSource from "./providerMetadata.ts?raw";
import walkthroughSource from "./AIWalkthrough.tsx?raw";
import readerSource from "../../pages/ReaderPage.tsx?raw";

describe("optional AI onboarding contracts", () => {
  it("is dismissible, non-blocking, and routes configuration to the AI section", () => {
    expect(onboardingSource).toContain("Enable Optional AI Features");
    expect(onboardingSource).toContain("Skip for now");
    expect(onboardingSource).toContain('onboardingDismissed: true');
    expect(onboardingSource).toContain('/settings?section=ai');
  });

  it("uses only the three official allowlisted provider links", () => {
    expect(metadataSource).toContain("https://aistudio.google.com/app/apikey");
    expect(metadataSource).toContain("https://ai.google.dev/gemini-api/docs/api-key");
    expect(metadataSource).toContain("https://ai.google.dev/gemini-api/docs");
    expect(metadataSource).toContain("This link is not approved by BookBuddy");
    expect(walkthroughSource).toContain('href={url}');
    expect(walkthroughSource).toContain('className="official-link"');
    expect(walkthroughSource).toContain("event.preventDefault()");
  });

  it("clears plaintext drafts and gates automatic analysis on explicit consent", () => {
    expect(settingsSource).toContain('setKeys([""])');
    expect(settingsSource).toContain('setVisionKeys([""])');
    expect(settingsSource).toContain("background_analysis_enabled");
    expect(readerSource).toContain("backgroundAnalysisEnabled &&");
  });
});
