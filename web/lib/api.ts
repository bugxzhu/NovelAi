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
};
