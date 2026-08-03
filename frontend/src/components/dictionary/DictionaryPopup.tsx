import * as Popover from "@radix-ui/react-popover";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Bot, LoaderCircle, Volume2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
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
  useEffect(() => { if (selectionKey !== "closed") { lookupStarted.current=performance.now(); recordedLookup.current=false; setAudioError(null); resetExplanation(); } }, [resetExplanation, selectionKey]);
  useEffect(() => { if (result.data && !recordedLookup.current && lookupStarted.current) { recordedLookup.current=true; recordPerformanceSample("dictionary_cached",performance.now()-lookupStarted.current); } }, [result.data]);

  const dictionary = result.data?.general_dictionary as DataRecord | undefined;
  const story = result.data?.story_glossary as DataRecord | undefined;
  const context = result.data?.context as DataRecord | undefined;
  const pronunciation = result.data?.pronunciation as DataRecord | undefined;
  const classification = result.data?.resolution?.classification;
  const popupAction = result.data?.routing.popup_action;
  const currentExplanation = explanation.variables?.selectionKey === selectionKey ? explanation.data : undefined;
  const senses = records(dictionary?.senses);
  const primarySense = senses[0];
  const contextMeaning = firstString(context?.meaning);
  const generalDefinition = firstString(primarySense?.definition);
  const definition = storyDefinition(story) ?? contextMeaning ?? generalDefinition;
  const partOfSpeech = firstString(dictionary?.part_of_speech) ?? firstString(primarySense?.pos);
  const synonyms = strings(primarySense?.synonyms).slice(0, 8);
  const examples = strings(primarySense?.examples).slice(0, 3);
  const variants = records(pronunciation?.variants);
  const recordedAudioId = variants.map((variant) => firstString(asRecord(variant.audio)?.audio_id)).find((value): value is string => Boolean(value));
  const canSpeakLocally = "speechSynthesis" in window && typeof SpeechSynthesisUtterance !== "undefined";
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

  if (popupAction === "suppress_popup") return null;
  return <Popover.Root open={Boolean(selection)} onOpenChange={(open) => { if (!open) onDismiss(); }}>
    <Popover.Anchor className="dictionary-anchor" style={selection?.anchorX !== undefined ? { left: selection.anchorX, top: selection.anchorY, bottom: "auto" } : undefined}/>
    <Popover.Portal>
      <Popover.Content
        className="dictionary-popup"
        side="top"
        align="center"
        sideOffset={18}
        collisionPadding={{ top: 74, right: 16, bottom: 54, left: 16 }}
        avoidCollisions
        sticky="always"
        onEscapeKeyDown={onDismiss}
        onPointerDownOutside={onDismiss}
        onInteractOutside={onDismiss}
      >
        <div className="dictionary-title"><div><p className="eyebrow">Dictionary & book context</p><h2>{selection?.text}</h2></div><Popover.Close aria-label="Close lookup"><X/></Popover.Close></div>
        {result.isLoading && <p className="dictionary-loading"><LoaderCircle className="spin"/>Looking up dictionary, context, and pronunciation…</p>}
        {result.error && <p role="alert">Dictionary services could not be reached. {result.error.message}</p>}
        {result.data && <>
          <p className="definition">{definition ?? "No definition was found for this selection."}</p>
          <p className="part-of-speech">{classification?.primary_class.replaceAll("_", " ") ?? partOfSpeech ?? "unknown"}</p>

          <section className="dictionary-section" aria-label="Contextual meaning">
            <h3>Context <span>{sectionStatus(context)}</span></h3>
            <p>{contextMeaning ?? "No distinct contextual sense was found for this sentence."}</p>
          </section>

          <section className="dictionary-section dictionary-ai" aria-label="Optional AI explanation"><h3>AI explanation <span>optional, on request</span></h3>{health.isLoading ? <p>Checking whether the optional AI companion is available…</p> : health.data?.capabilities.chapter_analysis ? currentExplanation ? <p>{currentExplanation.explanation}</p> : <button className="speak" disabled={explanation.isPending && explanation.variables?.selectionKey === selectionKey} onClick={() => { if (selection) explanation.mutate({ selectionKey, target: selection }); }}>{explanation.isPending && explanation.variables?.selectionKey === selectionKey ? <LoaderCircle className="spin"/> : <Bot/>}Ask AI about this wording</button> : <><p>AI features are offline because no usable API key is configured. Dictionary and spoiler-safe book context still work locally.</p><button className="speak" onClick={()=>setAIRequired(true)}><Bot/>Set up optional AI</button></>}{explanation.error && explanation.variables?.selectionKey === selectionKey && <small role="status">AI explanation could not be completed. Retry from this panel.</small>}</section>

          <section className="dictionary-section" aria-label="Book context">
            <h3>Book context <span>{sectionStatus(story)}</span></h3>
            <p>{storyDefinition(story) ?? (sectionStatus(story) === "unavailable" ? "Available after spoiler-safe chapter analysis is committed." : "No story-specific meaning has been established yet.")}</p>
          </section>

          <section className="dictionary-section" aria-label="General dictionary">
            <h3>General dictionary <span>{sectionStatus(dictionary)}</span></h3>
            <p>{generalDefinition ?? (sectionStatus(dictionary) === "not_applicable" ? "A general dictionary definition is not applicable to this named or grammatical reference." : "No general dictionary entry was found.")}</p>
            {examples.length > 0 && <ul>{examples.map((example) => <li key={example}>{example}</li>)}</ul>}
            {synonyms.length > 0 && <div className="chips" aria-label="Synonyms">{synonyms.map((word) => <span key={word}>{word}</span>)}</div>}
          </section>

          <section className="dictionary-section" aria-label="Pronunciation">
            <h3>Pronunciation <span>{sectionStatus(pronunciation)}</span></h3>
            {variants.length > 0 ? <div className="pronunciation-list">{variants.slice(0, 3).map((variant, index) => <p key={`${firstString(variant.variant) ?? "variant"}-${index}`}><strong>{firstString(variant.ipa) ?? ""}</strong>{firstString(variant.human_phonetic) && <span>{firstString(variant.human_phonetic)}</span>}</p>)}</div> : <p>No pronunciation variant is available.</p>}
            {(recordedAudioId || canSpeakLocally) && <button className="speak" onClick={() => void playPronunciation()}><Volume2/>{recordedAudioId ? "Play recorded pronunciation" : "Hear with Windows voice"}</button>}
            {audioError && <small role="status">{audioError}</small>}
          </section>
        </>}
        <Popover.Arrow className="popover-arrow"/>
      </Popover.Content>
    </Popover.Portal>
    <AIRequiredDialog open={aiRequired} feature="AI explanations" onOpenChange={setAIRequired}/>
  </Popover.Root>;
}
