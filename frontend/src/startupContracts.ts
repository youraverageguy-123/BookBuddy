export type StartupStage = "launching" | "startingBackend" | "connectingBackend" | "backendHealthy" | "loadingConfiguration" | "initializingReact" | "restoringSession" | "loadingLibrary" | "ready" | "transition" | "complete" | "failed";
export type StartupKind = "progress" | "slow" | "failure" | "ready";

export interface StartupEvent {
  attempt: number;
  stage: StartupStage;
  message: string;
  completedStages: number;
  totalStages: number;
  kind: StartupKind;
  actions: Array<"retry" | "exit">;
}
