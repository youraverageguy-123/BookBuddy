import { Maximize2, Minus, Plus } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { KnowledgeEntity, KnowledgeRelationship } from "../../api/knowledge";
import { layoutRelationshipGraph, nodeInitials, type GraphEdge, type GraphNode } from "./knowledgeModel";

const WIDTH = 960;
const HEIGHT = 600;
const MIN_ZOOM = 0.6;
const MAX_ZOOM = 3;
interface View { x: number; y: number; k: number }
const HOME: View = { x: 0, y: 0, k: 1 };

const nodeRadius = (node: GraphNode): number => 15 + Math.min(node.degree, 8) * 2.2;

/** A gentle arc between two nodes; the bend direction is stable per pair. */
function edgePath(edge: GraphEdge): string {
  const { source, target } = edge;
  const dx = target.x - source.x; const dy = target.y - source.y;
  const bend = ((source.id + target.id) % 2 === 0 ? 1 : -1) * 0.12;
  const cx = (source.x + target.x) / 2 - dy * bend; const cy = (source.y + target.y) / 2 + dx * bend;
  return `M ${source.x} ${source.y} Q ${cx} ${cy} ${target.x} ${target.y}`;
}

export function RelationshipGraph({ entities, relationships, selectedId, onSelect }: {
  entities: KnowledgeEntity[]; relationships: KnowledgeRelationship[]; selectedId: number | null; onSelect: (id: number) => void;
}) {
  const layout = useMemo(() => layoutRelationshipGraph(entities, relationships, WIDTH, HEIGHT), [entities, relationships]);
  const [view, setView] = useState<View>(HOME);
  const [hoveredId, setHoveredId] = useState<number | null>(null);
  const [hoveredEdge, setHoveredEdge] = useState<string | null>(null);
  const svg = useRef<SVGSVGElement>(null);
  const drag = useRef<{ pointer: number; startX: number; startY: number; view: View; moved: boolean } | null>(null);

  const zoomAt = useCallback((factor: number, px = WIDTH / 2, py = HEIGHT / 2) => setView((current) => {
    const k = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, current.k * factor));
    const ratio = k / current.k;
    // Keep the point under the cursor fixed while zooming.
    return { k, x: px - (px - current.x) * ratio, y: py - (py - current.y) * ratio };
  }), []);
  const toGraphPoint = useCallback((clientX: number, clientY: number) => {
    const box = svg.current?.getBoundingClientRect();
    if (!box || box.width === 0) return { x: WIDTH / 2, y: HEIGHT / 2 };
    return { x: ((clientX - box.left) / box.width) * WIDTH, y: ((clientY - box.top) / box.height) * HEIGHT };
  }, []);

  // React registers wheel listeners as passive, so the page would scroll while zooming.
  useEffect(() => {
    const element = svg.current;
    if (!element) return;
    const onWheel = (event: WheelEvent) => {
      // Plain scrolling stays with the page; Ctrl/Cmd + wheel (and trackpad pinch) zooms.
      if (!event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      const point = toGraphPoint(event.clientX, event.clientY);
      zoomAt(event.deltaY < 0 ? 1.15 : 1 / 1.15, point.x, point.y);
    };
    element.addEventListener("wheel", onWheel, { passive: false });
    return () => element.removeEventListener("wheel", onWheel);
  }, [toGraphPoint, zoomAt, layout.nodes.length]);

  if (layout.nodes.length === 0) return <p className="quiet-empty">No relationships have been found in the chapters you have finished.</p>;

  const focusId = hoveredId ?? selectedId;
  const linked = new Set<number>();
  if (focusId !== null) {
    for (const edge of layout.edges) {
      if (edge.source.id === focusId) linked.add(edge.target.id);
      if (edge.target.id === focusId) linked.add(edge.source.id);
    }
  }
  const activeEdge = layout.edges.find((edge) => edge.key === hoveredEdge);
  const focusNode = layout.nodes.find((node) => node.id === focusId);
  const caption = activeEdge ? activeEdge.details.join("  ·  ")
    : focusNode ? `${focusNode.name}: ${focusNode.degree} relationship${focusNode.degree === 1 ? "" : "s"}`
    : "Hover or select a character to trace their relationships. Drag to move; Ctrl + scroll to zoom.";

  return <figure className="relationship-graph">
    <div className="graph-stage">
      <svg ref={svg} viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="group" aria-label="Relationship map" className={drag.current?.moved ? "is-dragging" : ""}
        onPointerDown={(event) => { if ((event.target as Element).closest(".graph-node")) return; drag.current = { pointer: event.pointerId, startX: event.clientX, startY: event.clientY, view, moved: false }; event.currentTarget.setPointerCapture(event.pointerId); }}
        onPointerMove={(event) => {
          const state = drag.current;
          if (!state || state.pointer !== event.pointerId) return;
          const box = event.currentTarget.getBoundingClientRect();
          const dx = ((event.clientX - state.startX) / box.width) * WIDTH; const dy = ((event.clientY - state.startY) / box.height) * HEIGHT;
          if (Math.abs(dx) + Math.abs(dy) > 3) state.moved = true;
          if (state.moved) setView({ ...state.view, x: state.view.x + dx, y: state.view.y + dy });
        }}
        onPointerUp={(event) => { if (drag.current?.pointer === event.pointerId) drag.current = null; }}
        onPointerCancel={() => { drag.current = null; }}>
        <defs>
          <pattern id="graph-dots" width="28" height="28" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1.1" className="graph-dot"/></pattern>
          <radialGradient id="graph-person" cx="35%" cy="30%" r="80%"><stop offset="0%" className="node-stop-light"/><stop offset="100%" className="node-stop-dark"/></radialGradient>
          <radialGradient id="graph-other" cx="35%" cy="30%" r="80%"><stop offset="0%" className="node-stop-other-light"/><stop offset="100%" className="node-stop-other-dark"/></radialGradient>
          <filter id="graph-shadow" x="-50%" y="-50%" width="200%" height="200%"><feDropShadow dx="0" dy="3" stdDeviation="4" floodOpacity="0.35"/></filter>
        </defs>
        <rect className="graph-backdrop" x="0" y="0" width={WIDTH} height={HEIGHT} fill="url(#graph-dots)"/>
        <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
          {layout.edges.map((edge) => {
            const active = focusId === null || edge.source.id === focusId || edge.target.id === focusId;
            const path = edgePath(edge);
            return <g key={edge.key} className={`graph-edge ${edge.sentiment} ${active ? "" : "dimmed"} ${edge.key === hoveredEdge ? "hovered" : ""}`}
              onPointerEnter={() => setHoveredEdge(edge.key)} onPointerLeave={() => setHoveredEdge((current) => current === edge.key ? null : current)}>
              <path className="edge-line" d={path} strokeWidth={1.6 + edge.strength * 4}/>
              {/* A wide invisible stroke makes thin lines easy to hover. */}
              <path className="edge-hit" d={path}/>
              <title>{edge.details.join("\n")}</title>
            </g>;
          })}
          {layout.nodes.map((node) => {
            const active = focusId === null || node.id === focusId || linked.has(node.id);
            const radius = nodeRadius(node);
            const label = node.name.length > 22 ? `${node.name.slice(0, 21)}…` : node.name;
            return <g key={node.id} className={`graph-node ${node.id === selectedId ? "selected" : ""} ${active ? "" : "dimmed"} ${node.isPerson ? "" : "not-person"}`} transform={`translate(${node.x} ${node.y})`}
              role="button" tabIndex={0} aria-label={`${node.name}, ${node.degree} relationship${node.degree === 1 ? "" : "s"}`} aria-pressed={node.id === selectedId}
              onPointerEnter={() => setHoveredId(node.id)} onPointerLeave={() => setHoveredId((current) => current === node.id ? null : current)}
              onFocus={() => setHoveredId(node.id)} onBlur={() => setHoveredId((current) => current === node.id ? null : current)}
              onClick={() => onSelect(node.id)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect(node.id); } }}>
              <circle className="node-ring" r={radius + 6}/>
              <circle className="node-body" r={radius} fill={node.isPerson ? "url(#graph-person)" : "url(#graph-other)"} filter="url(#graph-shadow)"/>
              <text className="node-initials" textAnchor="middle" dominantBaseline="central" fontSize={Math.max(11, radius * 0.72)}>{nodeInitials(node.name)}</text>
              <text className="node-label" y={radius + 18} textAnchor="middle">{label}</text>
            </g>;
          })}
        </g>
      </svg>
      <div className="graph-controls" role="group" aria-label="Map zoom">
        <button aria-label="Zoom in" title="Zoom in" disabled={view.k >= MAX_ZOOM} onClick={() => zoomAt(1.25)}><Plus/></button>
        <button aria-label="Zoom out" title="Zoom out" disabled={view.k <= MIN_ZOOM} onClick={() => zoomAt(1 / 1.25)}><Minus/></button>
        <button aria-label="Reset view" title="Reset view" disabled={view.k === 1 && view.x === 0 && view.y === 0} onClick={() => setView(HOME)}><Maximize2/></button>
      </div>
    </div>
    <figcaption>
      <p className="graph-caption" aria-live="polite">{caption}</p>
      <div className="graph-legend">
        <span className="legend friendly">Warm</span><span className="legend hostile">Hostile</span><span className="legend mixed">Mixed</span><span className="legend neutral">Neutral</span>
        <span className="legend-note">Thicker lines mean stronger feelings</span>
        {layout.hidden > 0 && <span className="legend-note">Showing the {layout.nodes.length} most connected; {layout.hidden} more are in the Characters tab.</span>}
      </div>
    </figcaption>
  </figure>;
}
