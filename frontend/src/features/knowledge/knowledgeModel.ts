import type { KnowledgeEntity, KnowledgeRelationship } from "../../api/knowledge";

/**
 * The spoiler boundary: the highest chapter the reader has naturally finished.
 * Returns -1 when nothing is finished, which means "show no story knowledge".
 */
export function latestCompletedChapter(
  chapters: ReadonlyArray<{ session_key: string; chapter_index: number; naturally_completed: boolean }>,
  sessionKey: string,
): number {
  let latest = -1;
  for (const chapter of chapters) {
    if (chapter.session_key === sessionKey && chapter.naturally_completed) latest = Math.max(latest, chapter.chapter_index);
  }
  return latest;
}

/** "chapter 1" or "chapters 1–4": the finished range, for boundary messages. */
export const finishedChaptersLabel = (asOfChapter: number): string => asOfChapter <= 0 ? "chapter 1" : `chapters 1–${asOfChapter + 1}`;

export type Sentiment = "friendly" | "hostile" | "neutral";

export function relationshipSentiment(relationship: Pick<KnowledgeRelationship, "trust_score" | "hostility_score" | "respect_score" | "fear_score">): Sentiment {
  const warm = Math.max(relationship.trust_score ?? 0, 0) + Math.max(relationship.respect_score ?? 0, 0);
  const cold = Math.max(relationship.hostility_score ?? 0, 0) + Math.max(relationship.fear_score ?? 0, 0) + Math.max(-(relationship.trust_score ?? 0), 0);
  if (warm > cold) return "friendly";
  if (cold > warm) return "hostile";
  return "neutral";
}

/** How a pair of characters relate once both directions are considered. */
export type PairSentiment = Sentiment | "mixed";

export interface GraphNode { id: number; name: string; x: number; y: number; degree: number; isPerson: boolean }
export interface GraphEdge {
  key: string; source: GraphNode; target: GraphNode; sentiment: PairSentiment;
  /** 0–1: how strong the feelings are, from the largest score in either direction. */
  strength: number;
  /** One line per direction, for tooltips: "Aster → Beryl: warm". */
  details: string[];
}
export interface GraphLayout { nodes: GraphNode[]; edges: GraphEdge[]; hidden: number }

const sentimentWords: Record<Sentiment, string> = { friendly: "warm", hostile: "hostile", neutral: "neutral" };

function relationshipStrength(relationship: KnowledgeRelationship): number {
  const largest = Math.max(...[relationship.trust_score, relationship.hostility_score, relationship.respect_score, relationship.fear_score].map((score) => Math.abs(score ?? 0)));
  return Math.min(1, largest / 8);
}

/** Initials for a node badge: "Aster Vale" → "AV", "Greywater" → "G". */
export function nodeInitials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  const first = words[0]?.[0] ?? "?";
  const last = words.length > 1 ? words[words.length - 1]?.[0] ?? "" : "";
  return (first + last).toUpperCase();
}

/**
 * Deterministic force layout in a width × height box. Only connected entities
 * are drawn; the busiest `maxNodes` are kept so the picture stays readable.
 */
export function layoutRelationshipGraph(
  entities: ReadonlyArray<KnowledgeEntity>,
  relationships: ReadonlyArray<KnowledgeRelationship>,
  width: number,
  height: number,
  maxNodes = 36,
): GraphLayout {
  const degree = new Map<number, number>();
  for (const item of relationships) {
    degree.set(item.source_id, (degree.get(item.source_id) ?? 0) + 1);
    degree.set(item.target_id, (degree.get(item.target_id) ?? 0) + 1);
  }
  const connected = entities.filter((entity) => degree.has(entity.id))
    .sort((a, b) => (degree.get(b.id) ?? 0) - (degree.get(a.id) ?? 0) || a.name.localeCompare(b.name));
  const kept = connected.slice(0, maxNodes);
  const centerX = width / 2; const centerY = height / 2; const radius = Math.min(width, height) * 0.36;
  const nodes: GraphNode[] = kept.map((entity, index) => {
    const angle = (index / Math.max(kept.length, 1)) * Math.PI * 2;
    // The busiest entities start nearer the middle.
    const ring = radius * (0.35 + 0.65 * (index / Math.max(kept.length - 1, 1)));
    return { id: entity.id, name: entity.name, isPerson: entity.is_person, degree: degree.get(entity.id) ?? 0, x: centerX + Math.cos(angle) * ring, y: centerY + Math.sin(angle) * ring };
  });
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const edges: GraphEdge[] = [];
  const byPair = new Map<string, GraphEdge>();
  for (const item of relationships) {
    const source = byId.get(item.source_id); const target = byId.get(item.target_id);
    if (!source || !target || source === target) continue;
    const pair = source.id < target.id ? `${source.id}-${target.id}` : `${target.id}-${source.id}`;
    const sentiment = relationshipSentiment(item);
    const detail = `${source.name} → ${target.name}: ${sentimentWords[sentiment]}`;
    const existing = byPair.get(pair);
    if (existing) {
      // The reverse direction: a pair that disagrees is shown as mixed.
      if (existing.sentiment !== sentiment && existing.sentiment !== "mixed") {
        existing.sentiment = existing.sentiment === "neutral" ? sentiment : sentiment === "neutral" ? existing.sentiment : "mixed";
      }
      existing.strength = Math.max(existing.strength, relationshipStrength(item));
      if (!existing.details.includes(detail)) existing.details.push(detail);
      continue;
    }
    const edge: GraphEdge = { key: pair, source, target, sentiment, strength: relationshipStrength(item), details: [detail] };
    byPair.set(pair, edge);
    edges.push(edge);
  }

  const ideal = Math.sqrt((width * height) / Math.max(nodes.length, 1)) * 0.7;
  const margin = 46;
  for (let step = 0; step < 220; step += 1) {
    const cooling = 1 - step / 220;
    const moves = nodes.map((node) => ({ node, x: 0, y: 0 }));
    const moveOf = new Map(moves.map((move) => [move.node, move]));
    for (const [index, a] of moves.entries()) {
      for (const b of moves.slice(index + 1)) {
        let dx = a.node.x - b.node.x; let dy = a.node.y - b.node.y;
        if (dx === 0 && dy === 0) { dx = 0.5 + index * 0.01; dy = 0.5; }
        const distance = Math.max(Math.hypot(dx, dy), 1);
        const force = (ideal * ideal) / distance;
        a.x += (dx / distance) * force; a.y += (dy / distance) * force;
        b.x -= (dx / distance) * force; b.y -= (dy / distance) * force;
      }
    }
    for (const edge of edges) {
      const a = moveOf.get(edge.source); const b = moveOf.get(edge.target);
      if (!a || !b) continue;
      const dx = edge.source.x - edge.target.x; const dy = edge.source.y - edge.target.y;
      const distance = Math.max(Math.hypot(dx, dy), 1);
      const force = (distance * distance) / ideal;
      a.x -= (dx / distance) * force; a.y -= (dy / distance) * force;
      b.x += (dx / distance) * force; b.y += (dy / distance) * force;
    }
    for (const move of moves) {
      const { node } = move;
      // A gentle pull to the middle keeps separate clusters on the canvas.
      move.x += (centerX - node.x) * 0.06; move.y += (centerY - node.y) * 0.06;
      const length = Math.max(Math.hypot(move.x, move.y), 1);
      const limit = Math.min(length, 28 * cooling + 0.5);
      node.x = Math.min(width - margin, Math.max(margin, node.x + (move.x / length) * limit));
      // Extra room at the bottom keeps the name under each node inside the canvas.
      node.y = Math.min(height - margin - 26, Math.max(margin, node.y + (move.y / length) * limit));
    }
  }
  return { nodes, edges, hidden: connected.length - kept.length };
}
