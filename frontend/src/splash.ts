import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import type { StartupEvent } from "./startupContracts";

const message = document.querySelector<HTMLParagraphElement>("#startup-message")!;
const detail = document.querySelector<HTMLParagraphElement>("#startup-detail")!;
const progress = document.querySelector<HTMLDivElement>("#startup-progress")!;
const actions = document.querySelector<HTMLDivElement>("#startup-actions")!;
const retry = document.querySelector<HTMLButtonElement>("#startup-retry")!;
const exit = document.querySelector<HTMLButtonElement>("#startup-exit")!;

const segments = Array.from({ length: 6 }, () => {
  const segment = document.createElement("span");
  segment.className = "splash__segment";
  segment.setAttribute("aria-hidden", "true");
  progress.append(segment);
  return segment;
});

export function renderStartupEvent(event: StartupEvent): void {
  message.textContent = event.message;
  segments.forEach((segment, index) => segment.classList.toggle("is-complete", index < event.completedStages));
  const isSlow = event.kind === "slow";
  detail.hidden = !isSlow;
  detail.textContent = isSlow ? "BookBuddy is still working. No action is required." : "";
  actions.hidden = event.kind !== "failure";
  retry.hidden = !event.actions.includes("retry");
  exit.hidden = !event.actions.includes("exit");
}

retry.addEventListener("click", () => { actions.hidden = true; void invoke("startup_retry"); });
exit.addEventListener("click", () => { void invoke("startup_exit"); });

void listen<StartupEvent>("bookbuddy://startup-stage", ({ payload }) => renderStartupEvent(payload));
void listen("bookbuddy://begin-transition", () => {
  document.body.classList.add("is-leaving");
  const finish = () => { void invoke("startup_splash_faded"); };
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) finish();
  else window.setTimeout(finish, 170);
});

requestAnimationFrame(() => { void invoke("startup_splash_ready"); });
