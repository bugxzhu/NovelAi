// Mirrors app/models/*.py Pydantic schemas on the backend.
// Keep field names in snake_case to match JSON payloads — no transformation layer.

export interface Project {
  id: number;
  title: string;
  genre: string;
  premise: string;
  main_theme: string;
  tone: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreate {
  title: string;
  genre?: string;
  premise?: string;
  main_theme?: string;
  tone?: string;
}

export interface ProjectUpdate {
  title?: string;
  genre?: string;
  premise?: string;
  main_theme?: string;
  tone?: string;
}

export interface WorldOverview {
  id: number;
  project_id: number;
  setting_era: string;
  geography_summary: string;
  history_summary: string;
  culture_summary: string;
  power_system: string;
  rules_and_taboos: string;
  created_at: string;
  updated_at: string;
}

export interface WorldOverviewUpdate {
  setting_era?: string;
  geography_summary?: string;
  history_summary?: string;
  culture_summary?: string;
  power_system?: string;
  rules_and_taboos?: string;
}

export type LoreType =
  | "location"
  | "faction"
  | "item"
  | "organization"
  | "concept"
  | "custom";

export const LORE_TYPE_LABELS: Record<LoreType, string> = {
  location: "地点",
  faction: "势力",
  item: "物品",
  organization: "组织",
  concept: "概念",
  custom: "自定义",
};

export function loreTypeLabel(t: string): string {
  return LORE_TYPE_LABELS[t as LoreType] ?? t;
}

export interface LoreEntry {
  id: number;
  project_id: number;
  type: LoreType;
  name: string;
  title: string;
  description: string;
  attributes: Record<string, unknown>;
  parent_id: number | null;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface LoreCreate {
  project_id: number;
  type: LoreType;
  name: string;
  title?: string;
  description?: string;
  attributes?: Record<string, unknown>;
  parent_id?: number | null;
  tags?: string[];
}

export interface LoreUpdate {
  type?: LoreType;
  name?: string;
  title?: string;
  description?: string;
  attributes?: Record<string, unknown>;
  parent_id?: number | null;
  tags?: string[];
}

export interface Character {
  id: number;
  project_id: number;
  name: string;
  role: string;
  personality: Record<string, unknown>;
  speech_style: string;
  background: string;
  motivation: string;
  appearance: string;
  current_state: string;
  affiliations: number[];
  known_locations: number[];
  created_at: string;
  updated_at: string;
}

export interface CharacterCreate {
  project_id: number;
  name: string;
  role?: string;
  personality?: Record<string, unknown>;
  speech_style?: string;
  background?: string;
  motivation?: string;
  appearance?: string;
  current_state?: string;
  affiliations?: number[];
  known_locations?: number[];
}

export interface CharacterUpdate {
  name?: string;
  role?: string;
  personality?: Record<string, unknown>;
  speech_style?: string;
  background?: string;
  motivation?: string;
  appearance?: string;
  current_state?: string;
  affiliations?: number[];
  known_locations?: number[];
}

export interface Chapter {
  id: number;
  project_id: number;
  order_index: number;
  title: string;
  outline: string;
  content: string;
  status: string;
  plot_line_ids: number[];
  summary: string;
  content_hash: string;
  last_involved_character_ids: number[];
  last_location_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface ChapterCreate {
  project_id: number;
  order_index: number;
  title?: string;
  outline?: string;
  content?: string;
  status?: string;
}

export interface ChapterUpdate {
  order_index?: number;
  title?: string;
  outline?: string;
  content?: string;
  status?: string;
  summary?: string;
  last_involved_character_ids?: number[];
  last_location_id?: number | null;
}

export type ModelTask = "writer_long" | "writer_short";

export interface GenerateRequest {
  beat_text: string;
  instruction?: string;
  involved_character_ids: number[];
  location_id?: number | null;
  model_task?: ModelTask;
  max_tokens?: number;
}

export interface GenerationLogRead {
  id: number;
  chapter_id: number;
  project_id: number;
  beat_text: string;
  model: string | null;
  status: string;
  input_tokens: number;
  output_tokens: number;
  started_at: string;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface GenerationLogDetail extends GenerationLogRead {
  instruction: string;
  involved_character_ids: number[];
  location_id: number | null;
  system_prompt: string;
  user_prompt: string;
  context_summary: Record<string, unknown>;
  generated_text: string | null;
  model_task: string | null;
  stop_reason: string | null;
}

// Context bundle carried in the SSE context event
export interface ContextBundlePreview {
  project: {
    id: number;
    title: string;
    genre: string;
    main_theme: string;
    tone: string;
    premise: string;
  };
  world_overview: {
    setting_era: string;
    geography_summary: string;
    history_summary: string;
    culture_summary: string;
    power_system: string;
    rules_and_taboos: string;
  } | null;
  characters: Array<{
    id: number;
    name: string;
    role: string;
    current_state: string;
  }>;
  relationships: Array<{
    from: string;
    to: string;
    type: string;
    strength: number;
    description: string;
  }>;
  faction_lore: Array<{ id: number; name: string; description: string }>;
  location_lore: Array<{ id: number; name: string; description: string }>;
  recent_chapter_summaries: Array<{
    chapter_id: number;
    order_index: number;
    title: string;
    summary: string;
  }>;
}

// === M3a: Pending Updates ===

export interface PendingUpdateRead {
  id: number;
  project_id: number;
  chapter_id: number;
  update_type: string;
  operation: "create" | "update";
  target_table: "characters" | "lore_entries" | "character_states" | "relationships";
  target_id: number | null;
  reason: string;
  status: "pending" | "accepted" | "rejected";
  entity_name: string;
  entity_type: string;
  field_name: string;
  old_value: string;
  proposed_value: string;
  created_at: string;
  updated_at: string;
}

export interface PendingUpdateDetail extends PendingUpdateRead {
  proposed_change: Record<string, unknown>;
  decision_note: string;
  decided_at: string | null;
  extractor_model: string | null;
  extractor_log_id: number | null;
  chapter_title: string;
  target_entity_name: string | null;
}

export interface FinalizeResponse {
  chapter_id: number;
  summary: string;
  pending_created: number;
  log_id: number;
}

export type PendingStatus = "pending" | "accepted" | "rejected" | "all";

// === M3c-B: Character States ===

export interface CharacterState {
  id: number;
  character_id: number;
  chapter_id: number;
  chapter_title: string;
  chapter_order: number;
  state_snapshot: string;
  change_summary: string;
  extractor_log_id: number | null;
  pending_update_id: number | null;
  created_at: string;
  updated_at: string;
}

// === M3c-A: Relationships ===

export interface Relationship {
  id: number;
  project_id: number;
  from_char_id: number;
  from_char_name: string;
  to_char_id: number;
  to_char_name: string;
  type: string;
  strength: number;
  description: string;
  valid_from_chapter: number;
  valid_to_chapter: number | null;
  change_summary: string;
  extractor_log_id: number | null;
  pending_update_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface RelationshipCreate {
  project_id: number;
  from_char_id: number;
  to_char_id: number;
  type: string;
  strength?: number;
  description?: string;
  valid_from_chapter?: number;
  change_summary?: string;
}

export interface RelationshipUpdate {
  type?: string;
  strength?: number;
  description?: string;
}

export interface RelationshipHistoryItem {
  version_id: number;
  valid_from_chapter: number;
  valid_to_chapter: number | null;
  type: string;
  strength: number;
  description: string;
  change_summary: string;
  created_at: string;
}
