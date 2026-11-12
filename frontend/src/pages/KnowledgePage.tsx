import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, BookOpen, X } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { healthApi } from "../api/health";
import { knowledgeApi, type KnowledgeEntity, type KnowledgeEvent, type KnowledgeOverview } from "../api/knowledge";
import { CardGridSkeleton } from "../components/common/Skeleton";
import { ChatPanel } from "../features/knowledge/ChatPanel";
import { finishedChaptersLabel, knowledgeBoundary, relationshipSentiment } from "../features/knowledge/knowledgeModel";
import { RelationshipGraph } from "../features/knowledge/RelationshipGraph";
import { useLibraryModel } from "../hooks/useLibraryModel";
import { effectiveBookMetadata } from "../utils/bookMetadata";

type Tab = "characters" | "relationships" | "timeline" | "chat";
const tabs: { id: Tab; label: string }[] = [
  { id: "characters", label: "Characters" }, { id: "relationships", label: "Relationships" },
  { id: "timeline", label: "Timeline" }, { id: "chat", label: "Ask" },
];
const readable = (value: string | null | undefined): string => (value ?? "").replace(/_/g, " ").toLowerCase();
const known = (value: string | null | undefined): boolean => Boolean(value) && !["unknown", "uncertain", ""].includes(readable(value));

export default function KnowledgePage() {
  const params = useParams<{ book: string; session: string }>();
  const book = decodeURIComponent(params.book ?? ""); const session = decodeURIComponent(params.session ?? "");
  const sessionKey = `${book}::${session}`;
  const model = useLibraryModel();
  const [searchParams] = useSearchParams();
  const requestedTab = tabs.find((entry) => entry.id === searchParams.get("tab"))?.id;
  const [tab, setTab] = useState<Tab>(requestedTab ?? "characters");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const asOfChapter = useMemo(() => knowledgeBoundary(model.reader.data?.chapters ?? [], model.reader.data?.books ?? [], sessionKey), [model.reader.data?.books, model.reader.data?.chapters, sessionKey]);
  const progressReady = Boolean(model.reader.data) || !model.userId;
  const overview = useQuery({ queryKey: ["reader-knowledge", book, session, asOfChapter], queryFn: () => knowledgeApi.overview(book, session, asOfChapter), enabled: progressReady && Boolean(book && session) });
  const aiSettings = useQuery({ queryKey: ["ai-settings"], queryFn: healthApi.aiSettings, retry: false });
  const item = model.sessions.data?.sessions.find((candidate) => candidate.book_name === book && candidate.session_name === session);
  const readerLink = `/reader/${encodeURIComponent(book)}/${encodeURIComponent(session)}`;
  const data = overview.data;
  const selected = data?.entities.find((entity) => entity.id === selectedId) ?? null;

  return <main className="knowledge-page page-frame">
    <header className="page-intro">
      <Link className="back-link" to={`/book/${encodeURIComponent(book)}/${encodeURIComponent(session)}`}><ArrowLeft/>Book page</Link>
      <p className="eyebrow">Story knowledge</p>
      <h1>{item ? effectiveBookMetadata(item, model.stateBySession.get(item.session_key)).title : book.replace(/_/g, " ")}</h1>
      <p>{asOfChapter >= 0 ? `Everything here comes from ${finishedChaptersLabel(asOfChapter)}, which you have read. Later chapters stay hidden.` : "Nothing is shown until you finish a chapter, or tell BookBuddy how far you have already read on the book page."}</p>
    </header>
    <div className="knowledge-tabs" role="tablist" aria-label="Story knowledge views">
      {tabs.map((entry) => <button key={entry.id} role="tab" id={`knowledge-tab-${entry.id}`} aria-selected={tab === entry.id} aria-controls="knowledge-panel" className={tab === entry.id ? "active" : ""} onClick={() => setTab(entry.id)}>
        {entry.label}{data?.available && entry.id === "characters" ? <span>{data.entities.length}</span> : null}{data?.available && entry.id === "timeline" ? <span>{data.timeline.length}</span> : null}
      </button>)}
    </div>
    <div className={`knowledge-layout ${selected && tab !== "chat" ? "has-detail" : ""}`}>
      <section id="knowledge-panel" role="tabpanel" aria-labelledby={`knowledge-tab-${tab}`} className="knowledge-panel">
        {tab === "chat" ? <ChatPanel book={book} session={session} asOfChapter={asOfChapter} aiAvailable={Boolean(aiSettings.data?.capabilities.text)}/>
          : overview.isLoading || !progressReady ? <CardGridSkeleton label="Loading story knowledge"/>
          : overview.error ? <p className="quiet-empty" role="alert">Story knowledge could not be loaded. <button className="text-button" onClick={() => void overview.refetch()}>Try again</button></p>
          : !data?.available ? <EmptyKnowledge asOfChapter={asOfChapter} readerLink={readerLink} aiConfigured={Boolean(aiSettings.data?.capabilities.text)}/>
          : tab === "characters" ? <CharacterExplorer entities={data.entities} selectedId={selectedId} onSelect={setSelectedId}/>
          : tab === "relationships" ? <RelationshipGraph entities={data.entities} relationships={data.relationships} selectedId={selectedId} onSelect={(id) => setSelectedId((current) => current === id ? null : id)}/>
          : <Timeline events={data.timeline} onSelect={setSelectedId}/>}
      </section>
      {selected && data && tab !== "chat" && <EntityDetail book={book} session={session} entity={selected} overview={data} onClose={() => setSelectedId(null)} onSelect={setSelectedId}/>}
    </div>
  </main>;
}

function EmptyKnowledge({ asOfChapter, readerLink, aiConfigured }: { asOfChapter: number; readerLink: string; aiConfigured: boolean }) {
  return <div className="quiet-empty large"><div>
    <h2>{asOfChapter < 0 ? "Finish a chapter first" : "No story knowledge yet"}</h2>
    <p>{asOfChapter < 0 ? "BookBuddy builds this view chapter by chapter as you read."
      : aiConfigured ? "Your finished chapters have not been analyzed yet. Turn on background analysis in Settings, or keep reading and check back."
      : "Story knowledge is built by optional AI chapter analysis. Add a Gemini API key in Settings to turn it on."}</p>
    <p><Link className="primary" to={readerLink}><BookOpen/>Continue reading</Link> <Link className="secondary" to="/settings">Open settings</Link></p>
  </div></div>;
}

function CharacterExplorer({ entities, selectedId, onSelect }: { entities: KnowledgeEntity[]; selectedId: number | null; onSelect: (id: number) => void }) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"people" | "all">("people");
  const hasPeople = entities.some((entity) => entity.is_person);
  const needle = query.trim().toLowerCase();
  const visible = entities.filter((entity) => (filter === "all" || !hasPeople || entity.is_person) && (!needle || entity.name.toLowerCase().includes(needle)));
  return <div className="character-explorer">
    <div className="knowledge-filters">
      <input aria-label="Search characters" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search by name"/>
      {hasPeople && <div role="group" aria-label="Show">
        <button className={filter === "people" ? "active" : ""} aria-pressed={filter === "people"} onClick={() => setFilter("people")}>People</button>
        <button className={filter === "all" ? "active" : ""} aria-pressed={filter === "all"} onClick={() => setFilter("all")}>Everything</button>
      </div>}
    </div>
    {visible.length === 0 ? <p className="quiet-empty">No matches.</p> : <ul className="character-grid">
      {visible.map((entity) => <li key={entity.id}><button className={`character-card ${entity.id === selectedId ? "selected" : ""}`} aria-pressed={entity.id === selectedId} onClick={() => onSelect(entity.id)}>
        <span className="character-initial" aria-hidden="true">{entity.name.slice(0, 1).toUpperCase()}</span>
        <strong>{entity.name}</strong>
        <small>{[entity.is_person ? (known(entity.narrative_role) ? readable(entity.narrative_role) : "character") : readable(entity.entity_type), entity.first_seen_chapter !== null && entity.first_seen_chapter !== undefined ? `first seen in chapter ${entity.first_seen_chapter + 1}` : ""].filter(Boolean).join(" · ")}</small>
        <small>{entity.relationship_count} relationship{entity.relationship_count === 1 ? "" : "s"} · {entity.event_count} event{entity.event_count === 1 ? "" : "s"}</small>
      </button></li>)}
    </ul>}
  </div>;
}

function Timeline({ events, onSelect }: { events: KnowledgeEvent[]; onSelect: (id: number) => void }) {
  if (events.length === 0) return <p className="quiet-empty">No events have been recorded for the chapters you have finished.</p>;
  const chapters = new Map<number, KnowledgeEvent[]>();
  for (const event of events) chapters.set(event.chapter, [...(chapters.get(event.chapter) ?? []), event]);
  return <ol className="story-timeline">
    {[...chapters.entries()].map(([chapter, items]) => <li key={chapter}>
      <h2>Chapter {chapter + 1}</h2>
      <ul>{items.map((event) => <li key={event.id}>
        <p>{event.summary}</p>
        {(event.story_time || event.participants.length > 0) && <div className="timeline-meta">
          {event.story_time && <span>{event.story_time}</span>}
          {event.participants.map((participant) => <button key={participant.id} onClick={() => onSelect(participant.id)}>{participant.name}</button>)}
        </div>}
      </li>)}</ul>
    </li>)}
  </ol>;
}

function EntityDetail({ book, session, entity, overview, onClose, onSelect }: {
  book: string; session: string; entity: KnowledgeEntity; overview: KnowledgeOverview; onClose: () => void; onSelect: (id: number) => void;
}) {
  const detail = useQuery({ queryKey: ["reader-entity", book, session, entity.id, overview.as_of_chapter], queryFn: () => knowledgeApi.entity(book, session, entity.id, overview.as_of_chapter) });
  const relationships = overview.relationships.filter((item) => item.source_id === entity.id || item.target_id === entity.id);
  const others = new Map<number, { name: string; sentiment: string }>();
  for (const item of relationships) {
    const outgoing = item.source_id === entity.id;
    const otherId = outgoing ? item.target_id : item.source_id;
    // Prefer how this character feels about the other one over the reverse.
    if (outgoing || !others.has(otherId)) others.set(otherId, { name: outgoing ? item.target : item.source, sentiment: relationshipSentiment(item) });
  }
  const events = overview.timeline.filter((event) => event.participants.some((participant) => participant.id === entity.id));
  const aliases = (detail.data?.aliases ?? []).map((alias) => alias.name).filter((name) => name.toLowerCase() !== entity.name.toLowerCase());
  const facts = [
    entity.is_person ? "Character" : readable(entity.entity_type),
    known(entity.narrative_role) ? readable(entity.narrative_role) : "",
    known(entity.kind) ? readable(entity.kind) : "",
    known(entity.life_status) ? `${readable(entity.life_status_certainty)} ${readable(entity.life_status)}`.trim() : "",
  ].filter(Boolean);
  return <aside className="entity-detail" aria-label={`About ${entity.name}`}>
    <header><div><p className="eyebrow">As of chapter {overview.as_of_chapter + 1}</p><h2>{entity.name}</h2></div><button aria-label="Close details" onClick={onClose}><X/></button></header>
    <p className="entity-facts">{facts.join(" · ")}</p>
    {aliases.length > 0 && <p className="entity-aliases">Also called {aliases.join(", ")}</p>}
    <h3>Relationships</h3>
    {others.size === 0 ? <p className="quiet-note">None recorded yet.</p> : <ul className="entity-relationships">
      {[...others.entries()].map(([id, other]) => <li key={id}><button onClick={() => onSelect(id)}><span className={`legend ${other.sentiment}`}>{other.name}</span></button></li>)}
    </ul>}
    <h3>Events</h3>
    {events.length === 0 ? <p className="quiet-note">None recorded yet.</p> : <ul className="entity-events">
      {events.map((event) => <li key={event.id}><small>Chapter {event.chapter + 1}</small>{event.summary}</li>)}
    </ul>}
  </aside>;
}
