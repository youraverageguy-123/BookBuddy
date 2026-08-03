import { apiRequest } from "./client";
import { aiSettingsSchema, aiVerificationSchema, healthSchema } from "../types/contracts";
import { z } from "zod";

export const healthApi = {
  get: () => apiRequest("/health", healthSchema),
  aiSettings: () => apiRequest("/settings/ai", aiSettingsSchema),
  updateAiSettings: (apiKeys: string[], visionApiKeys: string[]) => apiRequest("/settings/ai", aiSettingsSchema, {
    method: "PUT", body: JSON.stringify({ api_keys: apiKeys, vision_api_keys: visionApiKeys }),
  }),
  patchAiSettings: (changes: { api_keys?: string[]; vision_api_keys?: string[]; background_analysis_enabled?: boolean }) => apiRequest("/settings/ai", aiSettingsSchema, { method: "PATCH", body: JSON.stringify(changes) }),
  removeAiSettings: () => apiRequest("/settings/ai", aiSettingsSchema, { method: "DELETE" }),
  verifyAi: (capability: "text" | "vision") => apiRequest("/settings/ai/verify", aiVerificationSchema, { method: "POST", body: JSON.stringify({ capability }) }),
  pauseBackgroundAnalysis: () => apiRequest("/settings/ai/background/pause", aiSettingsSchema, { method: "POST" }),
  resumeBackgroundAnalysis: () => apiRequest("/settings/ai/background/resume", aiSettingsSchema, { method: "POST" }),
  cancelBackgroundAnalysis: () => apiRequest("/settings/ai/background/cancel", z.object({ schema_version: z.literal("bookbuddy_ai_background_cancel_v1"), cancelled_count: z.number().int().nonnegative() }), { method: "POST" }),
  testCustom: async (url: string) => {
    let endpoint: URL;
    try {
      endpoint = new URL(url.trim());
    } catch {
      throw new Error("Enter a valid HTTP or HTTPS diagnostic URL.");
    }
    if (!(["http:", "https:"] as string[]).includes(endpoint.protocol)) {
      throw new Error("Enter a valid HTTP or HTTPS diagnostic URL.");
    }
    endpoint.pathname = `${endpoint.pathname.replace(/\/$/, "")}/health`;
    let response: Response;
    try {
      response = await fetch(endpoint.toString(), { headers: { Accept: "application/json" } });
    } catch {
      throw new Error("Could not reach the diagnostic backend. Make sure it is running and allows BookBuddy.");
    }
    if (!response.ok) throw new Error(`The diagnostic backend returned HTTP ${response.status}.`);
    try {
      return healthSchema.parse(await response.json());
    } catch {
      throw new Error("The URL responded, but it is not a compatible BookBuddy backend.");
    }
  },
};
