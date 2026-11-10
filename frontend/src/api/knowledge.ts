import { z } from "zod";
import { apiRequest, encoded } from "./client";

const score = z.number().nullable().optional();

export const knowledgeEntitySchema = z.object({
  id: z.number().int(), name: z.string(), entity_type: z.string(), is_person: z.boolean(),
  category: z.string().nullable().optional(), kind: z.string().nullable().optional(), narrative_role: z.string().nullable().optional(),
  first_seen_chapter: z.number().int().nullable().optional(),
  life_status: z.string().default("unknown"), life_status_certainty: z.string().default("unknown"),
  relationship_count: z.number().int(), event_count: z.number().int(),
});

export const knowledgeRelationshipSchema = z.object({
  relationship_key: z.string(), source_id: z.number().int(), target_id: z.number().int(), source: z.string(), target: z.string(),
  trust_score: score, hostility_score: score, respect_score: score, fear_score: score,
  last_observed_chapter: z.number().int().nullable().optional(),
});

export const knowledgeEventSchema = z.object({
  id: z.number().int(), chapter: z.number().int(), summary: z.string(), event_type: z.string(),
  story_time: z.string().nullable().optional(),
  participants: z.array(z.object({ id: z.number().int(), name: z.string(), role: z.string().nullable().optional() })),
});

export const knowledgeOverviewSchema = z.object({
  schema_version: z.literal("bookbuddy_reader_knowledge_v1"), as_of_chapter: z.number().int(), available: z.boolean(),
  entities: z.array(knowledgeEntitySchema), relationships: z.array(knowledgeRelationshipSchema), timeline: z.array(knowledgeEventSchema),
});

const entityDetailSchema = z.object({
  contract_version: z.string(), as_of_chapter: z.number().int(),
  aliases: z.array(z.object({ name: z.string() }).passthrough()).default([]),
  relationships: z.array(knowledgeRelationshipSchema.partial({ relationship_key: true }).passthrough()).default([]),
  events: z.array(z.object({ id: z.number().int(), chapter: z.number().int(), summary: z.string().nullable(), role: z.string().nullable().optional() }).passthrough()).default([]),
  status: z.object({ status: z.string().optional(), reader_state: z.string().optional() }).passthrough().optional(),
}).passthrough();

export const chatAnswerSchema = z.object({
  schema_version: z.literal("bookbuddy_reader_chat_v1"), answer: z.string(), as_of_chapter: z.number().int(),
  sources: z.array(z.object({ chapter_index: z.number().int(), chapter_title: z.string() })),
  grounding: z.object({ story_knowledge: z.boolean(), passages: z.number().int() }), provider: z.string(),
});

export type KnowledgeEntity = z.infer<typeof knowledgeEntitySchema>;
export type KnowledgeRelationship = z.infer<typeof knowledgeRelationshipSchema>;
export type KnowledgeEvent = z.infer<typeof knowledgeEventSchema>;
export type KnowledgeOverview = z.infer<typeof knowledgeOverviewSchema>;
export type ChatAnswer = z.infer<typeof chatAnswerSchema>;
export interface ChatTurn { role: "user" | "assistant"; text: string }

const root = (book: string, session: string) => `/reader/${encoded(book)}/${encoded(session)}`;

export const knowledgeApi = {
  overview: (book: string, session: string, asOfChapter: number) =>
    apiRequest(`${root(book, session)}/knowledge?as_of_chapter=${asOfChapter}`, knowledgeOverviewSchema),
  entity: (book: string, session: string, entityId: number, asOfChapter: number) =>
    apiRequest(`${root(book, session)}/entity/${entityId}?as_of_chapter=${asOfChapter}`, entityDetailSchema),
  chat: (book: string, session: string, question: string, asOfChapter: number, history: ChatTurn[]) =>
    apiRequest(`${root(book, session)}/chat`, chatAnswerSchema, {
      method: "POST",
      body: JSON.stringify({ question, as_of_chapter: asOfChapter, history: history.slice(-12) }),
    }),
};
