import { z } from "zod";
import { apiRequest, encoded } from "./client";

const databaseState = z.object({
  exists: z.boolean(), integrity: z.string(), size_bytes: z.number(),
  page_count: z.number().optional(), free_pages: z.number().optional(), reclaimable_ratio: z.number().optional(),
});
const maintenanceStatus = z.object({
  schema_version: z.literal("bookbuddy_database_maintenance_v1"),
  databases: z.record(z.string(), databaseState),
});
const resourceState = z.object({ size_bytes: z.number(), limit_bytes: z.number() });
const resourceStatus = z.object({
  schema_version: z.literal("bookbuddy_resources_v1"),
  resources: z.record(z.string(), resourceState),
});
const taskRecord = z.object({
  task_id: z.string(), task_type: z.string(), state: z.string(), progress: z.number(),
  user_message: z.string(), session_key: z.string(), updated_at: z.number(),
}).passthrough();
const taskStatus = z.object({ schema_version: z.literal("bookbuddy_tasks_v1"), tasks: z.array(taskRecord) });
const maintenanceResult = z.object({
  schema_version: z.literal("bookbuddy_database_maintenance_v1"),
  result: z.object({
    database: z.string(), status: z.string(), backup: z.string().optional(),
  }).passthrough(),
});
const pruneResult = z.object({
  schema_version: z.literal("bookbuddy_resources_v1"),
  result: z.object({
    namespace: z.string(), size_bytes: z.number(), limit_bytes: z.number(), removed: z.number(),
  }),
});

export const operationsApi = {
  maintenance: () => apiRequest("/maintenance/status", maintenanceStatus),
  maintain: (database: string) => apiRequest(`/maintenance/${encoded(database)}`, maintenanceResult, { method: "POST" }),
  resources: () => apiRequest("/resources/status", resourceStatus),
  prune: (namespace: string) => apiRequest(`/resources/${encoded(namespace)}/prune`, pruneResult, { method: "POST" }),
  tasks: () => apiRequest("/tasks", taskStatus),
};

export type MaintenanceStatus = z.infer<typeof maintenanceStatus>;
export type ResourceStatus = z.infer<typeof resourceStatus>;
export type TaskStatus = z.infer<typeof taskStatus>;
