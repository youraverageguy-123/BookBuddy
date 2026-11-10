import { useMemo } from "react";
import type { KnowledgeEntity, KnowledgeRelationship } from "../../api/knowledge";
import { layoutRelationshipGraph } from "./knowledgeModel";

const WIDTH = 960;
const HEIGHT = 600;

export function RelationshipGraph({ entities, relationships, selectedId, onSelect }: {
  entities: KnowledgeEntity[]; relationships: KnowledgeRelationship[]; selectedId: number | null; onSelect: (id: number) => void;
}) {
  const layout = useMemo(() => layoutRelationshipGraph(entities, relationships, WIDTH, HEIGHT), [entities, relationships]);
  if (layout.nodes.length === 0) return <p className="quiet-empty">No relationships have been found in the chapters you have finished.</p>;
  const linked = new Set<number>();
  if (selectedId !== null) {
    for (const edge of layout.edges) {
      if (edge.source.id === selectedId) linked.add(edge.target.id);
      if (edge.target.id === selectedId) linked.add(edge.source.id);
    }
  }
  return <figure className="relationship-graph">
    <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="group" aria-label="Relationship map">
      {layout.edges.map((edge) => {
        const active = selectedId === null || edge.source.id === selectedId || edge.target.id === selectedId;
        return <line key={edge.key} className={`graph-edge ${edge.sentiment} ${active ? "" : "dimmed"}`} x1={edge.source.x} y1={edge.source.y} x2={edge.target.x} y2={edge.target.y}/>;
      })}
      {layout.nodes.map((node) => {
        const active = selectedId === null || node.id === selectedId || linked.has(node.id);
        const radius = 9 + Math.min(node.degree, 8) * 1.6;
        return <g key={node.id} className={`graph-node ${node.id === selectedId ? "selected" : ""} ${active ? "" : "dimmed"} ${node.isPerson ? "" : "not-person"}`} transform={`translate(${node.x} ${node.y})`}
          role="button" tabIndex={0} aria-label={`${node.name}, ${node.degree} relationship${node.degree === 1 ? "" : "s"}`} aria-pressed={node.id === selectedId}
          onClick={() => onSelect(node.id)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect(node.id); } }}>
          <circle r={radius}/>
          <text y={radius + 15} textAnchor="middle">{node.name.length > 22 ? `${node.name.slice(0, 21)}…` : node.name}</text>
        </g>;
      })}
    </svg>
    <figcaption>
      <span className="legend friendly">Warm</span><span className="legend hostile">Hostile</span><span className="legend neutral">Neutral</span>
      {layout.hidden > 0 && <span>Showing the {layout.nodes.length} most connected; {layout.hidden} more are in the Characters tab.</span>}
    </figcaption>
  </figure>;
}
