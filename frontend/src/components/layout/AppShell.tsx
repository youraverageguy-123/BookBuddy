import { getCurrentWindow } from "@tauri-apps/api/window";
import { BookOpen, Home, Library, PanelLeft, Pin, PinOff, Settings } from "lucide-react";
import { useEffect } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useReaderStore } from "../../store/readerStore";

const links = [{to:"/",end:true,label:"Home",icon:Home},{to:"/library",label:"Library",icon:Library},{to:"/collections",label:"Collections",icon:BookOpen},{to:"/settings",label:"Settings",icon:Settings}] as const;

export function AppShell() {
  const library = useReaderStore((state) => state.library); const setPreferences = useReaderStore((state) => state.setLibraryPreferences);
  const collapsed = library.sidebarCollapsed && !library.sidebarPinned;
  useEffect(() => {
    if (!("__TAURI_INTERNALS__" in window)) return;
    void getCurrentWindow().setFullscreen(false).catch(() => undefined);
  }, []);
  return <div className={`app-shell ${collapsed ? "sidebar-collapsed" : ""}`}>
    <aside className="app-sidebar" onMouseEnter={() => { if (!library.sidebarPinned) setPreferences({sidebarCollapsed:false}); }} onMouseLeave={() => { if (!library.sidebarPinned) setPreferences({sidebarCollapsed:true}); }}>
      <div className="sidebar-top"><NavLink className="brand" to="/" title="BookBuddy"><img className="brand-logo" src="/bookbuddy-logo.png" alt=""/><span>BookBuddy</span></NavLink><button className="sidebar-control" aria-label={library.sidebarPinned?"Unpin sidebar":"Pin sidebar"} title={library.sidebarPinned?"Unpin sidebar":"Pin sidebar"} onClick={() => setPreferences({sidebarPinned:!library.sidebarPinned,sidebarCollapsed:false})}>{library.sidebarPinned?<PinOff/>:<Pin/>}</button></div>
      <nav aria-label="Primary navigation">{links.map((link) => {
        const Icon = link.icon;
        return <NavLink key={link.to} end={"end" in link ? link.end : undefined} to={link.to} title={link.label}><Icon aria-hidden="true"/><span>{link.label}</span></NavLink>;
      })}</nav>
      <div className="sidebar-bottom"><p className="sidebar-note">Your private reading room</p><button className="sidebar-control collapse-control" aria-label={collapsed?"Expand sidebar":"Collapse sidebar"} onClick={() => setPreferences({sidebarCollapsed:!library.sidebarCollapsed,sidebarPinned:false})}><PanelLeft/><span>{collapsed?"Expand":"Collapse"}</span></button></div>
    </aside>
    <div className="app-content"><Outlet /></div>
  </div>;
}
