import { apiRequest } from "./client";
import { aiSettingsSchema, healthSchema } from "../types/contracts";

export const healthApi = {
  get: () => apiRequest("/health", healthSchema),
  aiSettings: () => apiRequest("/settings/ai", aiSettingsSchema),
  updateAiSettings: (apiKeys: string[], visionApiKeys: string[]) => apiRequest("/settings/ai", aiSettingsSchema, {
    method: "PUT", body: JSON.stringify({ api_keys: apiKeys, vision_api_keys: visionApiKeys }),
  }),
  testCustom: async (url: string) => {
    const response = await fetch(`${url.replace(/\/$/, "")}/health`, { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`Diagnostic backend failed (${response.status})`);
    return healthSchema.parse(await response.json());
  },
};
