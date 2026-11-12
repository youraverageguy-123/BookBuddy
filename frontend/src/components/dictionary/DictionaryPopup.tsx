import * as Popover from "@radix-ui/react-popover";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Bot, LoaderCircle, Volume2, X } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { dictionaryApi } from "../../api/dictionary";
import { healthApi } from "../../api/health";
import { recordPerformanceSample } from "../../services/performance/recorder";
import { AIRequiredDialog } from "../../features/ai/AIRequiredDialog";

export interface SelectionInfo {
  text: string; context: string; chapter: number; knowledgeAsOfChapter: number;
  sentence?: string; previousSentence?: string; nextSentence?: string; paragraph?: string;
  sentenceSelectionStart?: number; sentenceSelectionEnd?: number; explainFunctionWords?: boolean;
  anchorX?: number; anchorY?: number;
}
interface Props { book: string; session: string; selection: SelectionInfo | null; onDismiss: () => void }

type DataRecord = Record<string, unknown>;
type TabId = "meaning" | "book" | "more" | "ai";
const tabs: { id: TabId; label: string }[] = [
  { id: "meaning", label: "Meaning" }, { id: "book", label: "In this book" }, { id: "more", label: "More" }, { id: "ai", label: "Ask AI" },
];

const asRecord = (value: unknown): DataRecord | null => value !== null && typeof value === "object" && !Array.isArray(value) ? value as DataRecord : null;
const firstString = (value: unknown): string | null => typeof value === "string" && value.trim() ? value : null;
const records = (value: unknown): DataRecord[] => Array.isArray(value) ? value.map(asRecord).filter((item): item is DataRecord => item !== null) : [];
const strings = (value: unknown): string[] => Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && Boolean(item.trim())) : [];
const sectionStatus = (section: DataRecord | undefined): string => firstString(section?.status) ?? "unavailable";
const storyDefinition = (story: DataRecord | undefined): string | null => {
  const definition = story?.definition;
  return firstString(definition) ?? firstString(asRecord(definition)?.text);
};

export function DictionaryPopup({ book, session, selection, onDismiss }: Props) {
  const [audioError, setAudioError] = useState<string | null>(null);
  const [aiRequired, setAIRequired] = useState(false);
  const [tab, setTab] = useState<TabId>("meaning");
  const lookupStarted = useRef(0); const recordedLookup = useRef(false);
  const selectionKey = selection ? `${selection.chapter}|${selection.text}|${selection.sentenceSelectionStart ?? ""}|${selection.context}` : "closed";
  const health = useQuery({ queryKey: ["health"], queryFn: healthApi.get, staleTime: 30_000, retry: false });
  const explanation = useMutation({ mutationFn: ({ target }: { selectionKey: string; target: SelectionInfo }) => dictionaryApi.explain(book, session, { chapterIndex: target.chapter, selectedText: target.text, contextText: target.context, knowledgeAsOfChapter: target.knowledgeAsOfChapter }) });
  const resetExplanation = explanation.reset;
  const result = useQuery({
    queryKey: ["dictionary", book, session, selection],
    queryFn: () => dictionaryApi.highlight(book, session, {
      chapterIndex: selection!.chapter,
      selectedText: selection!.text,
      contextText: selection!.context,
      knowledgeAsOfChapter: selection!.knowledgeAsOfChapter,
      sentenceText: selection!.sentence,
      previousSentence: selection!.previousSentence,
      nextSentence: selection!.nextSentence,
      paragraphText: selection!.paragraph,
      sentenceSelectionStart: selection!.sentenceSelectionStart,
      sentenceSelectionEnd: selection!.sentenceSelectionEnd,
      explainFunctionWords: selection!.explainFunctionWords,
    }),
    enabled: Boolean(selection),
    retry: false,
  });
  useEffect(() => { if (selectionKey !== "closed") { lookupStarted.current=performance.now(); recordedLookup.current=false; setAudioError(null); setTab("meaning"); resetExplanation(); } }, [resetExplanation, selectionKey]);
  useEffect(() => { if (result.data && !recordedLookup.current && lookupStarted.current) { recordedLookup.current=true; recordPerformanceSample("dictionary_cached",performance.now()-lookupStarted.current); } }, [result.data]);

  const dictionary = result.data?.general_dictionary as DataRecord | undefined;
  const story = result.data?.story_glossary as DataRecord | undefined;
  const context = result.data?.context as DataRecord | undefined;
  const pronunciation = result.data?.pronunciation as DataRecord | undefined;
  const classification = result.data?.resolution?.classification;
  const confidence = result.data?.routing.confidence ?? classification?.confidence;
  const popupAction = result.data?.routing.popup_action;
  const currentExplanation = explanation.variables?.selectionKey === selectionKey ? explanation.data : undefined;
  const explaining = explanation.isPending && explanation.variables?.selectionKey === selectionKey;
  const senses = records(dictionary?.senses);
  const primarySense = senses[0];
  const bookMeaning = storyDefinition(story);
  const contextMeaning = firstString(context?.meaning);
  const generalDefinition = firstString(primarySense?.definition);
  // One meaning leads the card: what the book has established, else this sentence's sense, else the dictionary's.
  const definition = bookMeaning ?? contextMeaning ?? generalDefinition;
  const definitionSource = bookMeaning ? "In this book" : contextMeaning ? "In this sentence" : generalDefinition ? "Dictionary" : null;
  // Show a real part of speech when the dictionary has one. The resolver's own class is only
  // useful when it says something a reader would recognise (pronoun, proper name, ...).
  const resolvedClass = classification?.primary_class.replaceAll("_", " ");
  const partOfSpeech = firstString(dictionary?.part_of_speech) ?? firstString(primarySense?.pos) ?? (resolvedClass && !["vocabulary", "unknown", "general"].includes(resolvedClass) ? resolvedClass : null);
  const synonyms = strings(primarySense?.synonyms).slice(0, 8);
  const examples = strings(primarySense?.examples).slice(0, 3);
  const otherSenses = senses.slice(1, 5).map((sense) => ({ text: firstString(sense.definition), pos: firstString(sense.pos) })).filter((sense) => sense.text);
  const variants = records(pronunciation?.variants);
  const phonetic = variants.map((variant) => firstString(variant.ipa) ?? firstString(variant.human_phonetic)).find((value): value is string => Boolean(value));
  const recordedAudioId = variants.map((variant) => firstString(asRecord(variant.audio)?.audio_id)).find((value): value is string => Boolean(value));
  const canSpeakLocally = "speechSynthesis" in window && typeof SpeechSynthesisUtterance !== "undefined";
  // Kept out of sight but available on hover when something looks wrong.
  const diagnostics = [
    `context: ${firstString(context?.provider) ?? sectionStatus(context)}`, `dictionary: ${firstString(dictionary?.provider) ?? sectionStatus(dictionary)}`,
    `book: ${sectionStatus(story)}`, typeof confidence === "number" ? `confidence ${Math.round(confidence * 100)}%` : "",
  ].filter(Boolean).join(" · ");
  useEffect(() => { if (popupAction === "suppress_popup") onDismiss(); }, [onDismiss, popupAction]);

  const speakLocally = () => {
    if (!selection || !canSpeakLocally) return;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(selection.text));
  };
  const playPronunciation = async () => {
    setAudioError(null);
    if (recordedAudioId) {
      try {
        const payload = await dictionaryApi.audio(recordedAudioId);
        const url = URL.createObjectURL(new Blob([payload]));
        const audio = new Audio(url);
        audio.addEventListener("ended", () => URL.revokeObjectURL(url), { once: true });
        await audio.play();
        return;
      } catch {
        setAudioError("Recorded audio failed; using the Windows voice instead.");
      }
    }
    speakLocally();
  };
  const onTabKey = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    event.preventDefault();
    const index = tabs.findIndex((entry) => entry.id === tab);
    const next = tabs[(index + (event.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
    if (!next) return;
    setTab(next.id);
    event.currentTarget.querySelector<HTMLButtonElement>(`#dict-tab-${next.id}`)?.focus();
  };

  // Open towards whichever half of the window has more room; the anchor sits at the top of
  // the selected word, so opening downwards needs extra offset to clear that line of text.
  const openBelow = (selection?.anchorY ?? Number.POSITIVE_INFINITY) < window.innerHeight / 2;
  if (popupAction === "suppress_popup") return null;
  return <Popover.Root open={Boolean(selection)} onOpenChange={(open) => { if (!open) onDismiss(); }}>
    <Popover.Anchor className="dictionary-anchor" style={selection?.anchorX !== undefined ? { left: selection.anchorX, top: selection.anchorY, bottom: "auto" } : undefined}/>
    <Popover.Portal>
      <Popover.Content
        className="dictionary-popup dict-card"
        side={openBelow ? "bottom" : "top"}
        align="center"
        sideOffset={openBelow ? 46 : 18}
        collisionPadding={{ top: 74, right: 16, bottom: 54, left: 16 }}
        avoidCollisions
        sticky="always"
        onEscapeKeyDown={onDismiss}
        onPointerDownOutside={onDismiss}
        onInteractOutside={onDismiss}
      >
        <header className="dict-head">
          <div className="dict-word">
            <h2>{selection?.text}</h2>
            {(phonetic || partOfSpeech) && <p>{phonetic && <span className="dict-phonetic">{phonetic}</span>}{partOfSpeech && <span className="dict-pos">{partOfSpeech}</span>}</p>}
          </div>
          {(recordedAudioId || canSpeakLocally) && <button type="button" className="dict-icon" aria-label="Hear pronunciation" title={recordedAudioId ? "Play recorded pronunciation" : "Hear with the Windows voice"} onClick={() => void playPronunciation()}><Volume2/></button>}
          <Popover.Close className="dict-icon" aria-label="Close lookup"><X/></Popover.Close>
        </header>

        {result.isLoading && <div className="dict-loading" role="status" aria-label="Looking up this word"><span className="skeleton-block"/><span className="skeleton-block"/><span className="skeleton-block short"/></div>}
        {result.error && <p className="dict-empty" role="alert">The dictionary could not be reached. Try selecting the word again.</p>}
        {result.data && <>
          <div className="dict-lead" title={diagnostics}>
            {definitionSource && <small>{definitionSource}</small>}
            <p className="definition">{definition ?? "No definition was found for this selection."}</p>
            {!definition && <button type="button" className="dict-link" onClick={() => setTab("ai")}>Ask AI instead</button>}
          </div>

          <div className="dict-tabs" role="tablist" aria-label="Lookup details" onKeyDown={onTabKey}>
            {tabs.map((entry) => <button key={entry.id} type="button" role="tab" id={`dict-tab-${entry.id}`} aria-selected={tab === entry.id} aria-controls="dict-panel"
              tabIndex={tab === entry.id ? 0 : -1} className={tab === entry.id ? "active" : ""} onClick={() => setTab(entry.id)}>{entry.label}</button>)}
          </div>

          <div className="dict-panel" id="dict-panel" role="tabpanel" aria-labelledby={`dict-tab-${tab}`}>
            {tab === "meaning" && <>
              {generalDefinition && generalDefinition !== definition && <p>{generalDefinition}</p>}
              {examples.length > 0 && <ul className="dict-examples">{examples.map((example) => <li key={example}>{example}</li>)}</ul>}
              {synonyms.length > 0 && <div className="chips" aria-label="Synonyms">{synonyms.map((word) => <span key={word}>{word}</span>)}</div>}
              {!(generalDefinition && generalDefinition !== definition) && examples.length === 0 && synonyms.length === 0 && <p className="dict-quiet">{sectionStatus(dictionary) === "not_applicable" ? "This is a name or a grammar word, so there is no dictionary entry for it." : "No examples or synonyms for this word."}</p>}
            </>}

            {tab === "book" && <p className={bookMeaning ? "" : "dict-quiet"}>{bookMeaning ?? (sectionStatus(story) === "unavailable" ? "Nothing yet. This fills in once the chapters you have read are analysed." : "The book has not given this word a special meaning so far.")}</p>}

            {tab === "more" && <>
              {otherSenses.length > 0 && <ol className="dict-senses">{otherSenses.map((sense) => <li key={sense.text}>{sense.pos && <em>{sense.pos}</em>}{sense.text}</li>)}</ol>}
              {variants.length > 0 && <div className="pronunciation-list">{variants.slice(0, 3).map((variant, index) => <p key={`${firstString(variant.variant) ?? "variant"}-${index}`}><strong>{firstString(variant.ipa) ?? ""}</strong>{firstString(variant.human_phonetic) && <span>{firstString(variant.human_phonetic)}</span>}</p>)}</div>}
              {otherSenses.length === 0 && variants.length === 0 && <p className="dict-quiet">No other meanings or pronunciations.</p>}
              {audioError && <small role="status">{audioError}</small>}
            </>}

            {tab === "ai" && <>
              {health.isLoading ? <p className="dict-quiet">Checking whether AI is set up…</p>
                : health.data?.capabilities.chapter_analysis ? currentExplanation ? <p>{currentExplanation.explanation}</p>
                  : <button type="button" className="speak" disabled={explaining} onClick={() => { if (selection) explanation.mutate({ selectionKey, target: selection }); }}>{explaining ? <LoaderCircle className="spin"/> : <Bot/>}Ask AI about this wording</button>
                : <><p className="dict-quiet">AI explanations need a Gemini API key. The dictionary and book context work without one.</p><button type="button" className="speak" onClick={() => setAIRequired(true)}><Bot/>Set up optional AI</button></>}
              {explanation.error && explanation.variables?.selectionKey === selectionKey && <small role="status">The AI explanation could not be completed. Try again.</small>}
            </>}
          </div>
        </>}
        <Popover.Arrow className="popover-arrow"/>
      </Popover.Content>
    </Popover.Portal>
    <AIRequiredDialog open={aiRequired} feature="AI explanations" onOpenChange={setAIRequired}/>
  </Popover.Root>;
}
