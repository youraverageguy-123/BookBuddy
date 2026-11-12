import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Cpu } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { healthApi } from "../../api/health";
import { toast } from "../../components/common/toast";

const failureReasons: Record<string, string> = {
  invalid_key: "the saved key was rejected", network_unavailable: "Gemini could not be reached", quota_exceeded: "the key's quota is used up",
  permission_denied: "the key lacks permission", region_unsupported: "Gemini is not available in this region", provider_unavailable: "the Gemini provider is not installed",
};

/** Lets the reader choose which Gemini model BookBuddy uses, from the models their key can access. */
export function ModelPicker({ currentModel, justSavedKey, onChanged }: { currentModel: string; justSavedKey: boolean; onChanged: () => void }) {
  const queryClient = useQueryClient();
  const section = useRef<HTMLElement>(null);
  const [custom, setCustom] = useState("");
  const models = useQuery({ queryKey: ["ai-models"], queryFn: healthApi.aiModels, retry: false, staleTime: 60_000 });
  const choose = useMutation({
    mutationFn: async (model: string) => {
      const settings = await healthApi.patchAiSettings({ model });
      // Confirm the key can actually use the model; the status card shows the outcome.
      await healthApi.verifyAi("text").catch(() => undefined);
      return settings;
    },
    onSuccess: (settings) => { toast.success(`Now using ${settings.models.text}.`); setCustom(""); void queryClient.invalidateQueries({ queryKey: ["ai-models"] }); onChanged(); },
  });
  useEffect(() => {
    if (!justSavedKey) return;
    void queryClient.invalidateQueries({ queryKey: ["ai-models"] });
    section.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    section.current?.querySelector("select")?.focus({ preventScroll: true });
  }, [justSavedKey, queryClient]);

  const listed = models.data?.models ?? [];
  const options = listed.some((model) => model.id === currentModel) || !currentModel ? listed : [{ id: currentModel, name: currentModel, description: "" }, ...listed];
  const selected = options.find((model) => model.id === currentModel);
  const listFailed = models.isError || (models.data !== undefined && models.data.status !== "ok");
  const customId = custom.trim();
  const customValid = /^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$/.test(customId);

  return <section ref={section} className={`operations-section model-picker ${justSavedKey ? "needs-choice" : ""}`}>
    <h3><Cpu/>Model</h3>
    {justSavedKey && <p className="diagnostic ok" role="status"><CheckCircle2/>Your key is saved. Choose the model BookBuddy should use.</p>}
    <label className="setting-row"><span>Gemini model<small>Used for chapter analysis, explanations, translation, and chat. Applies immediately.</small></span>
      <select value={currentModel} disabled={choose.isPending || models.isLoading} onChange={(event) => choose.mutate(event.target.value)}>
        {models.isLoading && <option value={currentModel}>Loading models…</option>}
        {!models.isLoading && options.map((model) => <option key={model.id} value={model.id}>{model.name === model.id ? model.id : `${model.name} (${model.id})`}</option>)}
      </select>
    </label>
    {selected?.description && <p className="settings-note">{selected.description}</p>}
    {listFailed && <p className="settings-note" role="status">The model list could not be loaded{models.data && failureReasons[models.data.status] ? ` because ${failureReasons[models.data.status]}` : ""}. You can still enter a model id below.</p>}
    <details open={listFailed || undefined}><summary>Enter a model id manually</summary>
      <form className="model-custom" onSubmit={(event) => { event.preventDefault(); if (customValid) choose.mutate(customId); }}>
        <input aria-label="Model id" value={custom} spellCheck={false} autoComplete="off" placeholder="for example gemini-2.5-flash" onChange={(event) => setCustom(event.target.value)}/>
        <button className="secondary" disabled={!customValid || choose.isPending}>Use this model</button>
      </form>
      {customId && !customValid && <p className="settings-note" role="alert">Model ids use only letters, numbers, dots, dashes, and underscores.</p>}
    </details>
    {choose.isPending && <p className="settings-note" role="status">Switching model and testing the connection…</p>}
    {choose.isSuccess && !choose.isPending && <p className="diagnostic ok" role="status"><CheckCircle2/>Now using {choose.data.models.text}.</p>}
    {choose.error && <p className="diagnostic" role="alert">The model could not be changed.</p>}
  </section>;
}
