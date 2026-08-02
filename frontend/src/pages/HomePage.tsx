import { ArrowRight, Clock3, Library, LoaderCircle } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { readerStateApi } from "../api/readerState";
import { BookActionController, BookCard } from "../components/library/BookCard";
import { BookCover } from "../components/library/BookCover";
import { useLibraryModel } from "../hooks/useLibraryModel";
import { useReaderStore } from "../store/readerStore";

export default function HomePage({ onReady }: { onReady?: () => void }) {
  const navigate = useNavigate(); const model = useLibraryModel(); const settings = useReaderStore();
  const [firstVisit] = useState(() => !useReaderStore.getState().library.hasCompletedFirstLaunch);
  const statistics = useQuery({queryKey:["reader-statistics",model.userId],queryFn:()=>readerStateApi.statistics(model.userId!),enabled:Boolean(model.userId)});
  useEffect(() => { if (model.sessions.isSuccess && model.reader.isSuccess) onReady?.(); }, [model.reader.isSuccess, model.sessions.isSuccess, onReady]);
  useEffect(() => { if (model.sessions.isSuccess && !settings.library.hasCompletedFirstLaunch) settings.setLibraryPreferences({hasCompletedFirstLaunch:true}); }, [model.sessions.isSuccess,settings]);
  if (model.sessions.isLoading || model.reader.isLoading) return <main className="home-loading page-frame" aria-busy="true"><div className="home-skeleton-title"/><div className="home-dashboard skeleton"><div/><div/><div/></div><span className="sr-only"><LoaderCircle/>Preparing your reading room…</span></main>;
  const sessions = model.sessions.data?.sessions ?? []; const userId = model.userId;
  if (!userId) return <main className="centered-state" role="alert">Reader profile unavailable.</main>;
  const pinned = new Set(settings.library.pinnedSessionKeys ?? []);
  const ordered = [...sessions].sort((a,b) => Number(pinned.has(b.session_key))-Number(pinned.has(a.session_key)) || (model.stateBySession.get(b.session_key)?.last_opened_at ?? 0)-(model.stateBySession.get(a.session_key)?.last_opened_at ?? 0));
  const continuing = ordered.find((item) => { const state=model.stateBySession.get(item.session_key); return state && state.book_progress>0 && !state.finished_at; }) ?? ordered[0];
  const recent = ordered.filter((item) => item.session_key !== continuing?.session_key).slice(0,4);
  const favorites = ordered.filter((item) => model.stateBySession.get(item.session_key)?.favorite).slice(0,4);
  const recentlyAdded = [...sessions].sort((a,b) => (b.imported_at ?? 0)-(a.imported_at ?? 0)).slice(0,4);
  const continueState=continuing?model.stateBySession.get(continuing.session_key):undefined;
  const eta=continuing?remainingEta(continuing.total_words ?? 0,continueState?.book_progress ?? 0,statistics.data?.statistics.per_book[continuing.session_key]):null;

  return <main className="home-page page-frame">
    <header className="home-welcome"><p>{firstVisit?"Welcome to BookBuddy":"Welcome back"}</p><span>Your stories are ready when you are.</span></header>
    {sessions.length===0 ? <section className="home-empty"><BookCover book="" session="" title="BookBuddy" featured/><h1>Your library is waiting.</h1><p>Import your first EPUB to begin a private reading room.</p><button className="primary" onClick={() => navigate("/library")}><Library/>Open Library</button></section> : <div className="home-dashboard">
      <section className="recent-dashboard"><ShelfHeading title="Recent Reads" to="/library" action="Open Library"/>{continuing && <div className="recent-mosaic"><BookActionController session={continuing} state={continueState} userId={userId} collections={model.collections}>{({open,showContextMenu}) => <button className="continue-cover" onClick={open} onContextMenu={showContextMenu}><BookCover featured book={continuing.book_name} session={continuing.session_name} title={continuing.book_title}/><span className="continue-copy"><small>Continue reading</small><strong>{continuing.book_title}</strong><span>{continuing.author || "Unknown author"}</span><span>Chapter {(continueState?.current_chapter ?? 0)+1} · {formatLastOpened(continueState?.last_opened_at)}</span><Progress value={continueState?.book_progress ?? 0}/><em><Clock3/>{eta ?? "Estimating reading time"}</em><b>Continue</b></span></button>}</BookActionController><div className="recent-mini-grid">{recent.map((item) => <MiniCover key={item.session_key} item={item} model={model}/>)}</div></div>}</section>
      <section className="favorite-dashboard"><ShelfHeading title="Favorite Books" to="/library" action="See all"/><CompactShelf items={favorites} empty="Favorite a book to keep it close." model={model}/></section>
      <section className="added-dashboard"><ShelfHeading title="Recently Added" to="/library" action="See all"/><CompactShelf items={recentlyAdded} empty="New imports will appear here." model={model}/></section>
    </div>}
  </main>;
}

function ShelfHeading({title,to,action}:{title:string;to:string;action:string}) { return <div className="section-heading"><h2>{title}</h2><Link to={to}>{action}<ArrowRight/></Link></div>; }
function Progress({value}:{value:number}) { return <div><div className="feature-progress"><span style={{width:`${Math.round(value*100)}%`}}/></div><small>{Math.round(value*100)}% complete</small></div>; }
function MiniCover({item,model}:{item:NonNullable<ReturnType<typeof useLibraryModel>["sessions"]["data"]>["sessions"][number];model:ReturnType<typeof useLibraryModel>}) { if (!model.userId) return null; return <BookActionController session={item} state={model.stateBySession.get(item.session_key)} userId={model.userId} collections={model.collections}>{({open,showContextMenu}) => <button className="mini-cover" onClick={open} onContextMenu={showContextMenu} title={item.book_title}><BookCover book={item.book_name} session={item.session_name} title={item.book_title}/><span>{item.book_title}</span></button>}</BookActionController>; }
function CompactShelf({items,empty,model}:{items:NonNullable<ReturnType<typeof useLibraryModel>["sessions"]["data"]>["sessions"];empty:string;model:ReturnType<typeof useLibraryModel>}) { if (!model.userId) return null; return items.length?<div className="compact-home-shelf">{items.map((item) => <BookCard compact key={item.session_key} session={item} state={model.stateBySession.get(item.session_key)} userId={model.userId!} collections={model.collections} bookmarkCount={(model.bookmarksBySession.get(item.session_key) ?? 0)+(model.annotationCounts.get(item.session_key) ?? 0)}/>)}</div>:<p className="quiet-empty">{empty}</p>; }
function formatLastOpened(value?:number|null):string { if(!value)return "not opened yet";const days=Math.max(0,Math.floor((Date.now()/1000-value)/86400));return days===0?"opened today":days===1?"opened yesterday":`opened ${days} days ago`; }
function remainingEta(totalWords:number,progress:number,personal?:{seconds_per_book:number|null;sufficient_data:boolean}):string|null { const seconds=personal?.sufficient_data&&personal.seconds_per_book?personal.seconds_per_book*Math.max(0,1-progress):totalWords>0?(totalWords*Math.max(0,1-progress)/240)*60:0;if(!seconds)return null;const minutes=Math.max(1,Math.round(seconds/60));return minutes<60?`${minutes} min remaining`:`${Math.floor(minutes/60)}h ${minutes%60}m remaining`; }
