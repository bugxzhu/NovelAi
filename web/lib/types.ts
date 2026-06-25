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
  content?: string;  // only present in single-chapter GET, not in list
  char_count?: number;  // present in list responses (computed by backend)
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
  plot_line_ids?: number[];
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
  target_table: "characters" | "lore_entries" | "character_states" | "relationships" | "events";
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

// === M3c-C: Events ===

export type EventFilter = "all" | "unpaid" | "paid";

export interface Event {
  id: number;
  project_id: number;
  chapter_id: number;
  chapter_title: string;
  chapter_order: number;
  title: string;
  description: string;
  involved_characters: number[];
  involved_character_names: string[];
  location_id: number | null;
  location_name: string;
  plot_line_id: number | null;
  foreshadows: number[];
  payoff_of: number[];
  payoff_of_titles: string[];
  is_unpaid: boolean;  // backend-derived: matches ?filter=unpaid decision
  extractor_log_id: number | null;
  pending_update_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface EventCreate {
  project_id: number;
  chapter_id: number;
  title: string;
  description: string;
  involved_characters?: number[];
  location_id?: number | null;
  plot_line_id?: number | null;
  foreshadows?: number[];
}

export interface EventUpdate {
  title?: string;
  description?: string;
  involved_characters?: number[];
  location_id?: number | null;
  plot_line_id?: number | null;
  foreshadows?: number[];
}

// === M4a: Reviewer ===

export type Severity = "error" | "warn" | "info";
export type Category = "character" | "relationship" | "plot" | "foreshadow" | "worldview";

export interface Issue {
  severity: Severity;
  category: Category;
  location: string;
  description: string;
  suggestion: string;
}

export interface ReviewResponse {
  chapter_id: number;
  issues: Issue[];
  log_id: number;
}

// === M3c-D: Plot Lines ===

export type PlotLineType = "main" | "sub";
export type PlotLineStatus = "planned" | "active" | "resolved" | "abandoned";

export interface PlotLine {
  id: number;
  project_id: number;
  type: PlotLineType;
  title: string;
  summary: string;
  description: string;
  status: PlotLineStatus;
  start_chapter: number | null;
  end_chapter: number | null;
  created_at: string;
  updated_at: string;
}

export interface PlotLineCreate {
  project_id: number;
  type?: PlotLineType;
  title: string;
  summary?: string;
  description?: string;
  status?: PlotLineStatus;
  start_chapter?: number | null;
  end_chapter?: number | null;
}

export interface PlotLineUpdate {
  type?: PlotLineType;
  title?: string;
  summary?: string;
  description?: string;
  status?: PlotLineStatus;
  start_chapter?: number | null;
  end_chapter?: number | null;
}

// === M4b-1: Story Milestones ===

export interface StoryMilestone {
  id: number;
  project_id: number;
  order_index: number;
  type: string;
  title: string;
  description: string;
  chapter_start: number | null;
  chapter_end: number | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface StoryMilestoneCreate {
  project_id: number;
  order_index?: number;
  type?: string;
  title: string;
  description?: string;
  chapter_start?: number | null;
  chapter_end?: number | null;
  status?: string;
}

export interface StoryMilestoneUpdate {
  order_index?: number;
  type?: string;
  title?: string;
  description?: string;
  chapter_start?: number | null;
  chapter_end?: number | null;
  status?: string;
}

// === M4b-2: Discuss ===

export interface DiscussBranch {
  label: string;
  title: string;
  summary: string;
  conflicts: string;
  opportunities: string;
  character_impact: string;
}

export interface DiscussRequest {
  question: string;
}

export interface DiscussResponse {
  question: string;
  branches: DiscussBranch[];
  recommended: string;
  reasoning: string;
  log_id: number;
}

// === Polish ===

export interface PolishRequest {
  selected_text?: string | null;
  direction?: string;
}

export interface PolishResponse {
  polished_texts: string[];
  is_selection: boolean;
  direction: string;
  log_id: number;
}

// === Genre Templates ===

export interface GenreTemplate {
  label: string;
  description: string;
  world_defaults: {
    power_system: string;
    rules_and_taboos: string;
  };
  character_archetypes: string[];
  plot_templates: string[];
}

// === Full-text search ===

export interface SearchResultChapter {
  id: number;
  title: string;
  order_index: number;
  match_type: "title" | "summary" | "content";
  snippet: string;
}

export interface SearchResultCharacter {
  id: number;
  name: string;
  role: string;
}

export interface SearchResultLore {
  id: number;
  name: string;
  type: string;
}

export interface SearchResultEvent {
  id: number;
  name: string;
  description: string;
}

export interface SearchResults {
  chapters: SearchResultChapter[];
  characters: SearchResultCharacter[];
  lore: SearchResultLore[];
  events: SearchResultEvent[];
}

// LLM settings (read-only). API keys come back masked from the server.
export interface LLMSettings {
  provider: string;
  anthropic: {
    api_key: string;
    base_url: string;
    model: string;
  };
  openai: {
    api_key: string;
    base_url: string;
    model: string;
  };
  embedding: {
    model: string;
    dimensions: number;
  };
  retrieval: {
    top_k: number;
    threshold: number;
  };
}

export interface LLMPingResponse {
  text: string;
  input_tokens: number;
  output_tokens: number;
}

// === Chapter Version History ===
export type ChapterVersionReason =
  | "manual"
  | "pre_ai_accept"
  | "pre_polish_accept"
  | "pre_finalize"
  | "pre_restore";

export interface ChapterVersionListItem {
  id: number;
  chapter_id: number;
  char_count: number;
  delta_char_count: number;
  reason: ChapterVersionReason;
  created_at: string;
}

export interface ChapterVersionRead {
  id: number;
  chapter_id: number;
  char_count: number;
  reason: ChapterVersionReason;
  created_at: string;
  content?: string | null;
}

export interface ChapterVersionCreate {
  content: string;
  reason: ChapterVersionReason;
}

export interface ChapterVersionRestoreResponse {
  restored_version_id: number;
  new_pre_restore_id: number;
  new_char_count: number;
}
