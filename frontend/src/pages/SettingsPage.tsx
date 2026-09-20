import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, BookOpen, Bot, CheckCircle2, Database, Download, Gauge, HardDrive, Info, Library, Search, Settings, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { healthApi } from "../api/health";
import { operationsApi } from "../api/operations";
import { readerStateApi } from "../api/readerState";
import { readerFontOptions } from "../reader/fonts";
import { applyStoredTheme, defaultPresentation, useReaderStore } from "../store/readerStore";
import packageMetadata from "../../package.json";
import { AISettingsPanel } from "../features/ai/AISettingsPanel";
import { exportReadingTelemetry } from "../services/telemetryExport";

const categories = [
  { id: "general", label: "General", icon: Settings }, { id: "reader", label: "Reader", icon: BookOpen }, { id: "library", label: "Library", icon: Library },
  { id: "dictionary", label: "Dictionary", icon: BookOpen }, { id: "ai", label: "AI", icon: Bot }, { id: "performance", label: "Performance", icon: Gauge }, { id: "advanced", label: "Advanced", icon: Database },
  { id: "about", label: "About", icon: Info },
] as const;
type Category = typeof categories[number]["id"];

export default function SettingsPage() {
  const state = useReaderStore(); const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const requestedCategory = searchParams.get("section");
  const [active, setActive] = useState<Category>(() => categories.some((category) => category.id === requestedCategory) ? requestedCategory as Category : "general"); const [settingsQuery,setSettingsQuery]=useState("");
  const [confirmReset, setConfirmReset] = useState(false); const [exportChoice, setExportChoice] = useState(false);
  const health = useQuery({ queryKey: ["health"], queryFn: healthApi.get, retry: false });
  const maintenance = useQuery({ queryKey: ["maintenance"], queryFn: operationsApi.maintenance, enabled: active === "advanced" });
  const resources = useQuery({ queryKey: ["resources"], queryFn: operationsApi.resources, enabled: active === "advanced" || active === "performance" });
  const tasks = useQuery({ queryKey: ["tasks"], queryFn: operationsApi.tasks, enabled: active === "advanced" });
  const diagnostic = useMutation({ mutationFn: healthApi.testCustom });
  const exportTelemetry = useMutation({ mutationFn: (destination: "choose" | "default") => exportReadingTelemetry(state.readerProfileId!, destination), onSuccess: (result) => { setExportChoice(false); if (result.status === "cancelled") exportTelemetry.reset(); } });
  const maintain = useMutation({ mutationFn: operationsApi.maintain, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["maintenance"] }) });
  const prune = useMutation({ mutationFn: operationsApi.prune, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["resources"] }) });
  const resetTelemetry = useMutation({ mutationFn: () => readerStateApi.resetStatistics(state.readerProfileId!), onSuccess: () => { setConfirmReset(false); void queryClient.invalidateQueries({ queryKey: ["reader-statistics"] }); } });
  const reader = state.global; const library = state.library;
  useEffect(() => { applyStoredTheme(); }, [reader.accent, reader.appTheme, reader.reducedMotion]);

  return <main className="settings-page page-frame">
    <header className="page-intro"><p className="eyebrow">A reading room shaped for you</p><h1>Settings</h1><p>Focused choices, organized without the endless scroll.</p><label className="settings-search"><Search/><span className="sr-only">Search settings</span><input value={settingsQuery} onChange={(event)=>setSettingsQuery(event.target.value)} placeholder="Search settings"/></label></header>
    <div className="settings-layout">
      <nav className="settings-nav" aria-label="Settings categories">{categories.filter(({label})=>!settingsQuery||label.toLowerCase().includes(settingsQuery.toLowerCase())).map(({ id, label, icon: Icon }) => <button key={id} className={active === id ? "active" : ""} aria-current={active === id ? "page" : undefined} onClick={() => setActive(id)}><Icon/>{label}</button>)}</nav>
      <section className="settings-panel">
        {active === "general" && <><h2>General</h2><p>Choose how BookBuddy opens and moves between screens.</p><SettingSelect label="Startup destination" value={library.startupDestination} onChange={(value) => state.setLibraryPreferences({ startupDestination: value as typeof library.startupDestination })} options={["home","library","resume"]}/><SettingSelect label="Page transitions" value={library.pageTransitions?"on":"off"} onChange={(value)=>state.setLibraryPreferences({pageTransitions:value==="on"})} options={["on","off"]}/><SettingSelect label="Application theme" value={reader.appTheme} onChange={(value) => state.setAppearance({ appTheme: value as typeof reader.appTheme })} options={["system","light","dark","contrast"]}/><SettingSelect label="Accent" value={reader.accent} onChange={(value) => state.setAppearance({ accent: value as typeof reader.accent })} options={["gold","brass","amber","sapphire","sage","rose"]}/><SettingSelect label="Motion" value={reader.reducedMotion} onChange={(value) => state.setAppearance({ reducedMotion: value as typeof reader.reducedMotion })} options={["system","reduce","full"]}/></>}
        {active === "reader" && <><h2>Reader defaults</h2><p>Books inherit these unless a book override is enabled.</p>
          <SettingSelect label="Theme" value={reader.readerTheme} onChange={(value) => state.setAppearance({ readerTheme: value as typeof reader.readerTheme })} options={["paper","night","sepia","oled","forest"]}/>
          <ReaderFontLibrary value={reader.usePublisherFonts ? "publisher" : reader.font} onChange={(value) => state.setAppearance(value === "publisher" ? { usePublisherFonts: true } : { usePublisherFonts: false, font: value })}/>
          <SettingSelect label="Reading mode" help="Paged lays the EPUB out like pages and can show a two-page spread. Continuous makes each chapter vertically scrollable." value={reader.readingMode} onChange={(value) => state.setAppearance({ readingMode: value as typeof reader.readingMode })} options={["paged","continuous"]}/>
          <SettingRange label="Font size" help="Changes reading-text size while preserving relative publisher heading and drop-cap sizes." value={reader.fontSize} min={14} max={38} step={1} suffix="px" onChange={(fontSize) => state.setAppearance({ fontSize })}/>
          <SettingRange label="Line height" help="Controls vertical space between lines of reading text." value={reader.lineSpacing} min={1.2} max={2.2} step={0.05} onChange={(lineSpacing) => state.setAppearance({ lineSpacing })}/>
          <SettingRange label="Paragraph spacing" help="Controls space after paragraphs; publisher indents, emphasis, and structural layout remain." value={reader.paragraphSpacing} min={0} max={2} step={0.1} suffix="em" onChange={(paragraphSpacing) => state.setAppearance({ paragraphSpacing })}/>
          <SettingRange label="Column width" value={reader.columnWidth} min={540} max={1100} step={20} suffix="px" onChange={(columnWidth) => state.setAppearance({ columnWidth })}/>
          <SettingRange label="Margins" value={reader.marginPercent} min={1} max={12} step={1} suffix="%" onChange={(marginPercent) => state.setAppearance({ marginPercent })}/>
          <SettingRange label="Image scale" value={reader.imageScale} min={0.5} max={1} step={0.05} suffix="×" onChange={(imageScale) => state.setAppearance({ imageScale })}/>
          <SettingSelect label="Text alignment" help="Left keeps an even left edge. Justify also aligns the right edge by adjusting word spacing." value={reader.justification} onChange={(value) => state.setAppearance({ justification: value as typeof reader.justification })} options={["left","justify"]}/>
          <SettingSelect label="Hyphenation" help="Allows long words to split at valid syllable boundaries at the end of a line. It can reduce large gaps in justified text." value={reader.hyphenation ? "on" : "off"} onChange={(value) => state.setAppearance({ hyphenation: value === "on" })} options={["off","on"]}/>
        </>}
        {active === "library" && <><h2>Library</h2><p>Choose how shelves open and arrange themselves.</p>
          <SettingSelect label="Default sort" value={library.sort} onChange={(value) => state.setLibraryPreferences({ sort: value as typeof library.sort })} options={["recent","added","title","author","progress"]}/>
          <SettingSelect label="Library view" value={library.density} onChange={(value) => state.setLibraryPreferences({ density: value as typeof library.density })} options={["grid","large","compact","detailed"]}/>
          <SettingSelect label="Startup destination" value={library.startupDestination} onChange={(value) => state.setLibraryPreferences({ startupDestination: value as typeof library.startupDestination })} options={["home","library","resume"]}/>
          <div className="settings-note">EPUB imports remain manual through drag-and-drop, Ctrl+O, or the Library command.</div>
        </>}
        {active === "ai" && <AISettingsPanel/>}
        {active === "dictionary" && <><h2>Dictionary</h2><p>Definitions and pronunciation stay local whenever possible.</p><SettingSelect label="Function words" value={reader.functionWordMode} onChange={(value) => state.setAppearance({ functionWordMode: value as typeof reader.functionWordMode })} options={["suppress","grammar"]}/><Capability ready={Boolean(health.data?.capabilities.dictionary)} label={health.data?.capabilities.dictionary ? "Offline dictionary ready" : "Offline dictionary data unavailable"}/><Capability ready={Boolean(health.data?.capabilities.pronunciation)} label={health.data?.capabilities.pronunciation ? "Local pronunciation ready" : "Pronunciation corpus unavailable"}/></>}
        {active === "performance" && <><h2>Performance</h2><p>BookBuddy lazy-loads covers, limits long result rendering, and keeps publisher EPUB layout stable.</p><Operations title="Derived caches" icon={<HardDrive/>}>{resources.data ? Object.entries(resources.data.resources).filter(([name]) => name !== "total").map(([name, cache]) => <OperationRow key={name} name={name} detail={`${formatBytes(cache.size_bytes)} of ${formatBytes(cache.limit_bytes)}`}><button className="secondary" disabled={prune.isPending} onClick={() => prune.mutate(name)}>Clean to limit</button></OperationRow>) : <p>Open Advanced once to load cache diagnostics.</p>}</Operations></>}
        {active === "advanced" && <><h2>Advanced</h2>
          <div className={`diagnostic ${health.data ? "ok" : ""}`}><Activity/>{health.isLoading ? "Checking managed backend…" : health.data ? `Managed BookBuddy ${health.data.version} is ready` : "Managed backend is offline"}</div>
          <label className="setting-row"><span>Diagnostic backend URL<small>This never replaces the packaged managed backend.</small></span><input value={state.customBackendUrl} onChange={(event) => { state.setDiagnosticBackendUrl(event.target.value); diagnostic.reset(); }}/></label>
          <button className="secondary" disabled={diagnostic.isPending} onClick={() => diagnostic.mutate(state.customBackendUrl)}>{diagnostic.isPending ? "Testing diagnostic URL…" : "Test diagnostic URL"}</button>
          {diagnostic.isSuccess && <p className="diagnostic ok" role="status"><CheckCircle2/>Backend {diagnostic.data.version} is ready.</p>}
          {diagnostic.isError && <p className="diagnostic" role="alert">{diagnostic.error.message}</p>}
          <Operations title="Databases" icon={<Database/>}>{maintenance.data ? Object.entries(maintenance.data.databases).map(([name, database]) => <OperationRow key={name} name={name} detail={`${database.integrity} · ${formatBytes(database.size_bytes)}`}><button className="secondary" disabled={maintain.isPending || database.integrity !== "ok"} onClick={() => maintain.mutate(name)}>{maintain.isPending ? "Working…" : "Back up & optimize"}</button></OperationRow>) : <p>Loading database status…</p>}{maintain.isSuccess && <p className="diagnostic ok" role="status"><CheckCircle2/>Database backup and optimization completed.</p>}{maintain.isError && <p className="diagnostic" role="alert">Database maintenance could not be completed. Your data was not changed.</p>}</Operations>
          <Operations title="Derived caches" icon={<HardDrive/>}>{resources.data ? Object.entries(resources.data.resources).filter(([name]) => name !== "total").map(([name, cache]) => <OperationRow key={name} name={name} detail={`${formatBytes(cache.size_bytes)} of ${formatBytes(cache.limit_bytes)}`}><button className="secondary" disabled={prune.isPending} onClick={() => prune.mutate(name)}>{prune.isPending ? "Cleaning…" : "Clean to limit"}</button></OperationRow>) : <p>Loading cache status…</p>}{prune.isSuccess && <p className="diagnostic ok" role="status"><CheckCircle2/>Cache cleanup completed.</p>}{prune.isError && <p className="diagnostic" role="alert">Cache cleanup could not be completed. No books or reading data were changed.</p>}</Operations>
          <Operations title="Background work" icon={<Activity/>}><p>{tasks.data ? `${tasks.data.tasks.filter((task) => ["queued","running","paused"].includes(task.state)).length} active or queued · ${tasks.data.tasks.length} recorded` : "Loading task status…"}</p></Operations>
          <Operations title="Local reading data" icon={<BookOpen/>}><p>Reading time and progress estimates stay on this device and never include selected text.</p><div className="operation-actions"><button className="secondary" disabled={!state.readerProfileId || exportTelemetry.isPending} onClick={() => { exportTelemetry.reset(); setExportChoice(true); }}><Download/>{exportTelemetry.isPending ? "Exporting…" : "Export"}</button><button className="secondary danger-outline" disabled={!state.readerProfileId} onClick={() => setConfirmReset(true)}><Trash2/>Reset telemetry</button></div>{exportTelemetry.isSuccess && exportTelemetry.data.status === "saved" && <p className="diagnostic ok" role="status"><CheckCircle2/>Reading data exported to <code>{exportTelemetry.data.path}</code></p>}{exportTelemetry.isError && <p className="diagnostic" role="alert">Reading data could not be exported. No reading data was changed.</p>}</Operations>
          <button className="text-action" onClick={() => state.setAppearance(defaultPresentation)}>Reset appearance defaults</button>
        </>}
        {active === "about" && <><h2>About BookBuddy</h2><p>Version {packageMetadata.version}</p><p>A private, local-first reading application with an optional AI companion.</p><div className="settings-note">Tauri 2 · React 19 · epub.js · FastAPI</div></>}
      </section>
    </div>
    {confirmReset && <div className="dialog-overlay"><section className="book-dialog" role="dialog" aria-modal="true" aria-label="Reset reading telemetry"><button className="dialog-x" aria-label="Close" onClick={() => setConfirmReset(false)}><X/></button><h2>Reset reading telemetry?</h2><p>This removes local reading-time sessions and ETA learning. Books, progress, notes, bookmarks, and settings are preserved.</p><button className="primary danger" disabled={resetTelemetry.isPending} onClick={() => resetTelemetry.mutate()}>Reset telemetry</button><button className="secondary" onClick={() => setConfirmReset(false)}>Keep data</button></section></div>}
    {exportChoice && <div className="dialog-overlay"><section className="book-dialog" role="dialog" aria-modal="true" aria-label="Choose export location"><button className="dialog-x" aria-label="Close" onClick={() => setExportChoice(false)}><X/></button><h2>Export reading data</h2><p>Choose where BookBuddy should save your local reading data.</p><button className="primary" onClick={() => exportTelemetry.mutate("choose")}><Download/>Choose location…</button><button className="secondary" onClick={() => exportTelemetry.mutate("default")}>Use BookBuddy default folder</button><button className="secondary" onClick={() => setExportChoice(false)}>Cancel</button></section></div>}
  </main>;
}

function SettingHelp({ text }: { text: string }) {
  return <span className="setting-help" tabIndex={0} aria-label={text} data-tooltip={text}><Info/></span>;
}
function SettingSelect({ label, value, options, onChange, help }: { label: string; value: string; options: string[]; onChange: (value: string) => void; help?: string }) {
  return <label className="setting-row"><span>{label}{help && <SettingHelp text={help}/>}</span><select value={value} onChange={(event) => onChange(event.target.value)}>{options.map((option) => <option key={option} value={option}>{option.replaceAll("-", " ").replace(/^./, (letter) => letter.toUpperCase())}</option>)}</select></label>;
}
function SettingRange({ label, value, min, max, step, suffix = "", help, onChange }: { label: string; value: number; min: number; max: number; step: number; suffix?: string; help?: string; onChange: (value: number) => void }) {
  const updateValue = (event: React.FormEvent<HTMLInputElement>) => onChange(Number(event.currentTarget.value));
  return <label className="setting-row range"><span>{label}{help && <SettingHelp text={help}/>}<output>{value}{suffix}</output></span><input type="range" value={value} min={min} max={max} step={step} onInput={updateValue} onChange={updateValue}/></label>;
}
function ReaderFontLibrary({ value, onChange }: { value: "publisher" | typeof readerFontOptions[number]["id"]; onChange: (value: "publisher" | typeof readerFontOptions[number]["id"]) => void }) {
  const groups = [...new Set(readerFontOptions.map((font) => font.group))];
  return <label className="setting-row"><span>Font library<SettingHelp text="Original EPUB font uses the book's embedded or named typefaces. Other choices replace only the font face; publisher headings, drop caps, indents, emphasis, and layout remain."/><small>Changes the font face only. EPUB drop caps, headings, image layout, and paragraph formatting are preserved.</small></span><select value={value} onChange={(event) => onChange(event.target.value as "publisher" | typeof readerFontOptions[number]["id"])}><option value="publisher">Original EPUB font & styling</option>{groups.map((group) => <optgroup key={group} label={group}>{readerFontOptions.filter((font) => font.group === group).map((font) => <option key={font.id} value={font.id} style={{fontFamily:font.family}}>{font.label} — {font.description}</option>)}</optgroup>)}</select></label>;
}
function Capability({ ready, label }: { ready: boolean; label: string }) { return <div className={`capability ${ready ? "ready" : ""}`}>{ready ? <CheckCircle2/> : <Activity/>}<span>{label}</span></div>; }
function Operations({ title, icon, children }: { title: string; icon: ReactNode; children: ReactNode }) { return <section className="operations-section"><h3>{icon}{title}</h3>{children}</section>; }
function OperationRow({ name, detail, children }: { name: string; detail: string; children: ReactNode }) { return <div className="operation-row"><span><strong>{name}</strong><small>{detail}</small></span>{children}</div>; }

function formatBytes(value: number): string { if (value < 1024) return `${value} B`; if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`; return `${(value / (1024 * 1024)).toFixed(1)} MB`; }
