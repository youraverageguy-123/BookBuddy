import { describe, expect, it } from "vitest";
import type { KnowledgeEntity, KnowledgeRelationship } from "../../api/knowledge";
import { latestCompletedChapter, layoutRelationshipGraph, nodeInitials, relationshipSentiment } from "./knowledgeModel";

const entity = (id: number, name: string): KnowledgeEntity => ({
  id, name, entity_type: "INDIVIDUAL", is_person: true, life_status: "unknown", life_status_certainty: "unknown", relationship_count: 0, event_count: 0,
});
const relationship = (source: number, target: number, trust: number): KnowledgeRelationship => ({
  relationship_key: `${source}::${target}`, source_id: source, target_id: target, source: `e${source}`, target: `e${target}`, trust_score: trust,
});

describe("story knowledge model", () => {
  it("uses the highest naturally finished chapter of this book as the spoiler boundary", () => {
    const chapters = [
      { session_key: "A::Reading", chapter_index: 0, naturally_completed: true },
      { session_key: "A::Reading", chapter_index: 3, naturally_completed: true },
      { session_key: "A::Reading", chapter_index: 5, naturally_completed: false },
      { session_key: "B::Reading", chapter_index: 9, naturally_completed: true },
    ];
    expect(latestCompletedChapter(chapters, "A::Reading")).toBe(3);
    expect(latestCompletedChapter(chapters, "C::Reading")).toBe(-1);
  });

  it("classifies relationship sentiment from the scores", () => {
    expect(relationshipSentiment({ trust_score: 4 })).toBe("friendly");
    expect(relationshipSentiment({ trust_score: -6 })).toBe("hostile");
    expect(relationshipSentiment({ trust_score: 1, hostility_score: 5 })).toBe("hostile");
    expect(relationshipSentiment({})).toBe("neutral");
  });

  it("lays out only connected entities, inside the canvas, without overlap", () => {
    const entities = [entity(1, "Aster"), entity(2, "Beryl"), entity(3, "Corvin"), entity(4, "Loner")];
    const layout = layoutRelationshipGraph(entities, [relationship(1, 2, 4), relationship(2, 1, 3), relationship(3, 1, -6)], 800, 500);
    expect(layout.nodes.map((node) => node.name).sort()).toEqual(["Aster", "Beryl", "Corvin"]);
    expect(layout.edges).toHaveLength(2);
    const pair = layout.edges.find((edge) => edge.key === "1-2");
    expect(pair?.sentiment).toBe("friendly");
    expect(pair?.details).toEqual(["Aster → Beryl: warm", "Beryl → Aster: warm"]);
    expect(pair?.strength).toBe(0.5);
    const rivalry = layoutRelationshipGraph(entities, [relationship(1, 3, 4), relationship(3, 1, -8)], 800, 500).edges[0];
    expect(rivalry?.sentiment).toBe("mixed");
    expect(rivalry?.strength).toBe(1);
    expect(nodeInitials("Aster Vale")).toBe("AV");
    expect(nodeInitials("Greywater")).toBe("G");
    for (const node of layout.nodes) {
      expect(node.x).toBeGreaterThanOrEqual(0); expect(node.x).toBeLessThanOrEqual(800);
      expect(node.y).toBeGreaterThanOrEqual(0); expect(node.y).toBeLessThanOrEqual(500);
    }
    for (const left of layout.nodes) {
      for (const right of layout.nodes) {
        if (left !== right) expect(Math.hypot(left.x - right.x, left.y - right.y)).toBeGreaterThan(40);
      }
    }
    expect(layoutRelationshipGraph(entities, [relationship(1, 2, 1)], 800, 500)).toEqual(layoutRelationshipGraph(entities, [relationship(1, 2, 1)], 800, 500));
  });

  it("keeps only the busiest entities when there are too many", () => {
    const entities = Array.from({ length: 12 }, (_, index) => entity(index + 1, `E${index + 1}`));
    const relationships = entities.slice(1).map((item) => relationship(1, item.id, 1));
    const layout = layoutRelationshipGraph(entities, relationships, 800, 500, 5);
    expect(layout.nodes).toHaveLength(5);
    expect(layout.hidden).toBe(7);
    expect(layout.nodes[0]?.name).toBe("E1");
  });
});
