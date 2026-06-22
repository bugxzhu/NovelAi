import type {
  Project, ProjectCreate, ProjectUpdate,
  WorldOverview, WorldOverviewUpdate,
  LoreEntry, LoreCreate, LoreUpdate,
  Character, CharacterCreate, CharacterUpdate,
  Chapter, ChapterCreate, ChapterUpdate,
  GenerationLogRead, GenerationLogDetail,
  PendingUpdateRead, PendingUpdateDetail,
  FinalizeResponse, PendingStatus,
  CharacterState,
  Relationship, RelationshipCreate, RelationshipUpdate, RelationshipHistoryItem,
  Event, EventCreate, EventUpdate, EventFilter,
  PlotLine, PlotLineCreate, PlotLineUpdate, PlotLineStatus,
  StoryMilestone, StoryMilestoneCreate, StoryMilestoneUpdate,
  Issue, ReviewResponse,
  DiscussBranch, DiscussRequest, DiscussResponse,
  PolishRequest, PolishResponse,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8005";

export class ApiError extends Error {
  constructor(public status: number, public body: unknown) {
    super(`HTTP ${status}`);
    this.name = "ApiError";
  }
}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: "include",
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      body = await res.text().catch(() => null);
    }
    throw new ApiError(res.status, body);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function qs(params: Record<string, unknown>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null) continue;
    sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export const api = {
  // Projects
  listProjects: () => http<Project[]>("/api/projects"),
  getProject: (id: number) => http<Project>(`/api/projects/${id}`),
  createProject: (data: ProjectCreate) =>
    http<Project>("/api/projects", { method: "POST", body: JSON.stringify(data) }),
  updateProject: (id: number, data: ProjectUpdate) =>
    http<Project>(`/api/projects/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteProject: (id: number) =>
    http<void>(`/api/projects/${id}`, { method: "DELETE" }),

  // World overview
  getWorldOverview: (projectId: number) =>
    http<WorldOverview | null>(`/api/projects/${projectId}/world-overview`),
  updateWorldOverview: (projectId: number, data: WorldOverviewUpdate) =>
    http<WorldOverview>(`/api/projects/${projectId}/world-overview`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  // Lore
  listLore: (projectId: number, type?: string) =>
    http<LoreEntry[]>(`/api/lore${qs({ project_id: projectId, type })}`),
  createLore: (data: LoreCreate) =>
    http<LoreEntry>("/api/lore", { method: "POST", body: JSON.stringify(data) }),
  updateLore: (id: number, data: LoreUpdate) =>
    http<LoreEntry>(`/api/lore/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteLore: (id: number) =>
    http<void>(`/api/lore/${id}`, { method: "DELETE" }),

  // Characters
  listCharacters: (projectId: number) =>
    http<Character[]>(`/api/characters${qs({ project_id: projectId })}`),
  getCharacter: (id: number) => http<Character>(`/api/characters/${id}`),
  createCharacter: (data: CharacterCreate) =>
    http<Character>("/api/characters", { method: "POST", body: JSON.stringify(data) }),
  updateCharacter: (id: number, data: CharacterUpdate) =>
    http<Character>(`/api/characters/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteCharacter: (id: number) =>
    http<void>(`/api/characters/${id}`, { method: "DELETE" }),

  // Chapters
  listChapters: (projectId: number) =>
    http<Chapter[]>(`/api/chapters${qs({ project_id: projectId })}`),
  getChapter: (id: number) => http<Chapter>(`/api/chapters/${id}`),
  createChapter: (data: ChapterCreate) =>
    http<Chapter>("/api/chapters", { method: "POST", body: JSON.stringify(data) }),
  updateChapter: (id: number, data: ChapterUpdate) =>
    http<Chapter>(`/api/chapters/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteChapter: (id: number) =>
    http<void>(`/api/chapters/${id}`, { method: "DELETE" }),

  // Generation logs (M2b: project_id supported)
  listGenerationLogs: (params: { chapter_id?: number; project_id?: number; limit?: number; offset?: number }) =>
    http<GenerationLogRead[]>(`/api/generation-logs${qs(params as Record<string, unknown>)}`),
  getGenerationLog: (id: number) =>
    http<GenerationLogDetail>(`/api/generation-logs/${id}`),

  // M3a: Pending Updates
  listPendingUpdates: (params: {
    project_id: number;
    status?: PendingStatus;
    chapter_id?: number;
    limit?: number;
    offset?: number;
  }) =>
    http<PendingUpdateRead[]>(`/api/pending-updates${qs(params as Record<string, unknown>)}`),
  getPendingUpdate: (id: number) =>
    http<PendingUpdateDetail>(`/api/pending-updates/${id}`),
  acceptPendingUpdate: (id: number) =>
    http<PendingUpdateRead>(`/api/pending-updates/${id}/accept`, { method: "POST" }),
  rejectPendingUpdate: (id: number, note?: string) =>
    http<PendingUpdateRead>(`/api/pending-updates/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ note: note ?? "" }),
    }),
  finalizeChapter: (chapterId: number) =>
    http<FinalizeResponse>(`/api/chapters/${chapterId}/finalize`, { method: "POST" }),

  // M4a: Reviewer
  reviewChapter: (chapterId: number) =>
    http<ReviewResponse>(`/api/chapters/${chapterId}/review`, { method: "POST" }),

  // M4b-2: Discuss
  discussChapter: (chapterId: number, question: string, selectedText?: string) =>
    http<DiscussResponse>(`/api/chapters/${chapterId}/discuss`, {
      method: "POST",
      body: JSON.stringify({ question, selected_text: selectedText }),
    }),

  // Polish
  polishChapter: (chapterId: number, selectedText?: string) =>
    http<PolishResponse>(`/api/chapters/${chapterId}/polish`, {
      method: "POST",
      body: JSON.stringify({ selected_text: selectedText || null } as PolishRequest),
    }),

  // M3c-B: Character States
  listCharacterStates: (
    characterId: number,
    opts?: { order?: "desc" | "asc"; limit?: number },
  ) =>
    http<CharacterState[]>(
      `/api/characters/${characterId}/states${qs({
        order: opts?.order ?? "desc",
        limit: opts?.limit ?? 20,
      } as Record<string, unknown>)}`,
    ),

  // M3c-A: Relationships
  listRelationships: (projectId: number, opts?: { includeHistory?: boolean; limit?: number }) =>
    http<Relationship[]>(
      `/api/relationships${qs({
        project_id: projectId,
        include_history: opts?.includeHistory ? "true" : undefined,
        limit: opts?.limit ?? 200,
      } as Record<string, unknown>)}`,
    ),
  getRelationshipHistory: (fromCharId: number, toCharId: number) =>
    http<RelationshipHistoryItem[]>(
      `/api/relationships/history${qs({ from_char_id: fromCharId, to_char_id: toCharId })}`,
    ),
  createRelationship: (data: RelationshipCreate) =>
    http<Relationship>("/api/relationships", { method: "POST", body: JSON.stringify(data) }),
  updateRelationship: (id: number, data: RelationshipUpdate) =>
    http<Relationship>(`/api/relationships/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteRelationship: (id: number) =>
    http<void>(`/api/relationships/${id}`, { method: "DELETE" }),
  softCloseRelationship: (id: number, validToChapter: number) =>
    http<Relationship>(`/api/relationships/${id}/soft-close`, {
      method: "POST",
      body: JSON.stringify({ valid_to_chapter: validToChapter }),
    }),

  // M3c-C: Events
  listEvents: (projectId: number, opts?: { chapterId?: number; filter?: EventFilter }) =>
    http<Event[]>(
      `/api/events${qs({
        project_id: projectId,
        chapter_id: opts?.chapterId,
        filter: opts?.filter ?? "all",
      } as Record<string, unknown>)}`,
    ),
  getEvent: (id: number) => http<Event>(`/api/events/${id}`),
  createEvent: (data: EventCreate) =>
    http<Event>("/api/events", { method: "POST", body: JSON.stringify(data) }),
  updateEvent: (id: number, data: EventUpdate) =>
    http<Event>(`/api/events/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteEvent: (id: number) =>
    http<void>(`/api/events/${id}`, { method: "DELETE" }),

  // M3c-D: Plot Lines
  listPlotLines: (projectId: number, status?: PlotLineStatus) =>
    http<PlotLine[]>(`/api/plot-lines${qs({ project_id: projectId, status })}`),
  createPlotLine: (data: PlotLineCreate) =>
    http<PlotLine>("/api/plot-lines", { method: "POST", body: JSON.stringify(data) }),
  updatePlotLine: (id: number, data: PlotLineUpdate) =>
    http<PlotLine>(`/api/plot-lines/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deletePlotLine: (id: number) =>
    http<void>(`/api/plot-lines/${id}`, { method: "DELETE" }),

  // M4b-1: Story Milestones
  listStoryMilestones: (projectId: number) =>
    http<StoryMilestone[]>(`/api/story-milestones${qs({ project_id: projectId })}`),
  createStoryMilestone: (data: StoryMilestoneCreate) =>
    http<StoryMilestone>("/api/story-milestones", { method: "POST", body: JSON.stringify(data) }),
  updateStoryMilestone: (id: number, data: StoryMilestoneUpdate) =>
    http<StoryMilestone>(`/api/story-milestones/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteStoryMilestone: (id: number) =>
    http<void>(`/api/story-milestones/${id}`, { method: "DELETE" }),
};
