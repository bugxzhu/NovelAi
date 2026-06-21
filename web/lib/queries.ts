"use client";

import {
  useQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { api } from "./api";
import type {
  ProjectCreate, ProjectUpdate,
  WorldOverviewUpdate,
  LoreCreate, LoreUpdate,
  CharacterCreate, CharacterUpdate,
  ChapterCreate, ChapterUpdate,
  PendingStatus,
  RelationshipCreate, RelationshipUpdate,
  EventCreate, EventUpdate, EventFilter,
  PlotLineCreate, PlotLineUpdate, PlotLineStatus,
} from "./types";

// Projects
export function useProjects() {
  return useQuery({ queryKey: ["projects"], queryFn: () => api.listProjects() });
}
export function useProject(id: number) {
  return useQuery({ queryKey: ["project", id], queryFn: () => api.getProject(id) });
}
export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: ProjectCreate) => api.createProject(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });
}
export function useUpdateProject(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: ProjectUpdate) => api.updateProject(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["project", id] });
      qc.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}
export function useDeleteProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deleteProject(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });
}

// World overview
export function useWorldOverview(projectId: number) {
  return useQuery({
    queryKey: ["world-overview", projectId],
    queryFn: () => api.getWorldOverview(projectId),
  });
}
export function useUpdateWorldOverview(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: WorldOverviewUpdate) => api.updateWorldOverview(projectId, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["world-overview", projectId] }),
  });
}

// Lore
export function useLore(projectId: number, type?: string) {
  return useQuery({
    queryKey: ["lore", projectId, type],
    queryFn: () => api.listLore(projectId, type),
  });
}
export function useCreateLore() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: LoreCreate) => api.createLore(data),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["lore", data.project_id] });
    },
  });
}
export function useUpdateLore(id: number, projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: LoreUpdate) => api.updateLore(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["lore", projectId] }),
  });
}
export function useDeleteLore(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deleteLore(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["lore", projectId] }),
  });
}

// Characters
export function useCharacters(projectId: number) {
  return useQuery({
    queryKey: ["characters", projectId],
    queryFn: () => api.listCharacters(projectId),
  });
}
export function useCreateCharacter() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CharacterCreate) => api.createCharacter(data),
    onSuccess: (data) => qc.invalidateQueries({ queryKey: ["characters", data.project_id] }),
  });
}
export function useUpdateCharacter(id: number, projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CharacterUpdate) => api.updateCharacter(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["characters", projectId] }),
  });
}
export function useDeleteCharacter(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deleteCharacter(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["characters", projectId] }),
  });
}

// Chapters
export function useChapters(projectId: number) {
  return useQuery({
    queryKey: ["chapters", projectId],
    queryFn: () => api.listChapters(projectId),
  });
}
export function useChapter(id: number) {
  return useQuery({
    queryKey: ["chapter", id],
    queryFn: () => api.getChapter(id),
  });
}
export function useCreateChapter() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: ChapterCreate) => api.createChapter(data),
    onSuccess: (data) => qc.invalidateQueries({ queryKey: ["chapters", data.project_id] }),
  });
}
// Note: requires projectId for cache scoping. Callers must pass it (e.g. useChapterAutosave(chapterId, projectId)).
export function useUpdateChapter(id: number, projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: ChapterUpdate) => api.updateChapter(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["chapter", id] });
      qc.invalidateQueries({ queryKey: ["chapters", projectId] });
    },
  });
}
export function useDeleteChapter(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deleteChapter(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["chapters", projectId] }),
  });
}

// Generation logs
export function useGenerationLogsByChapter(chapterId: number) {
  return useQuery({
    queryKey: ["generation-logs", "chapter", chapterId],
    queryFn: () => api.listGenerationLogs({ chapter_id: chapterId }),
  });
}
export function useGenerationLogsByProject(projectId: number) {
  return useQuery({
    queryKey: ["generation-logs", "project", projectId],
    queryFn: () => api.listGenerationLogs({ project_id: projectId }),
  });
}
export function useGenerationLog(id: number) {
  return useQuery({
    queryKey: ["generation-log", id],
    queryFn: () => api.getGenerationLog(id),
  });
}

// === M3a: Pending Updates ===

export function usePendingUpdates(
  projectId: number,
  status: PendingStatus = "pending",
  chapterId?: number
) {
  return useQuery({
    queryKey: ["pending-updates", projectId, status, chapterId],
    queryFn: () => api.listPendingUpdates({ project_id: projectId, status, chapter_id: chapterId }),
  });
}

export function usePendingCount(projectId: number) {
  return useQuery({
    queryKey: ["pending-count", projectId],
    queryFn: async () => {
      const list = await api.listPendingUpdates({
        project_id: projectId,
        status: "pending",
        limit: 200,
      });
      return list.length;
    },
    staleTime: 5_000,
  });
}

export function useAcceptPendingUpdate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.acceptPendingUpdate(id),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["pending-updates"] });
      qc.invalidateQueries({ queryKey: ["pending-count"] });
      qc.invalidateQueries({ queryKey: ["characters"] });
      qc.invalidateQueries({ queryKey: ["lore"] });
      // M3c-B: character_states target_id is null; invalidate all character-states
      // caches (single-user, low cardinality) when a state change is accepted
      if (data.target_table === "character_states") {
        qc.invalidateQueries({ queryKey: ["character-states"] });
      }
      // M3c-A: relationships target_id is null; invalidate all relationships caches
      if (data.target_table === "relationships") {
        qc.invalidateQueries({ queryKey: ["relationships"] });
        qc.invalidateQueries({ queryKey: ["relationship-history"] });
      }
      // M3c-C: events target_id is null; invalidate all events caches
      if (data.target_table === "events") {
        qc.invalidateQueries({ queryKey: ["events"] });
      }
    },
  });
}

export function useRejectPendingUpdate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, note }: { id: number; note?: string }) =>
      api.rejectPendingUpdate(id, note),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pending-updates"] });
      qc.invalidateQueries({ queryKey: ["pending-count"] });
    },
  });
}

// === M3c-B: Character States ===

export function useCharacterStates(
  characterId: number | null,
  opts?: { order?: "desc" | "asc"; limit?: number },
) {
  return useQuery({
    queryKey: ["character-states", characterId, opts?.order ?? "desc", opts?.limit],
    queryFn: () => api.listCharacterStates(characterId!, opts),
    enabled: characterId != null,
  });
}

// === M3c-A: Relationships ===

export function useRelationships(projectId: number, opts?: { includeHistory?: boolean }) {
  return useQuery({
    queryKey: ["relationships", projectId, opts?.includeHistory ?? false],
    queryFn: () => api.listRelationships(projectId, opts),
  });
}

export function useRelationshipHistory(
  fromId: number | null,
  toId: number | null,
) {
  return useQuery({
    queryKey: ["relationship-history", fromId, toId],
    queryFn: () => api.getRelationshipHistory(fromId!, toId!),
    enabled: fromId != null && toId != null,
  });
}

export function useCreateRelationship() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: RelationshipCreate) => api.createRelationship(data),
    onSuccess: (data) =>
      qc.invalidateQueries({ queryKey: ["relationships", data.project_id] }),
  });
}

export function useUpdateRelationship(id: number, projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: RelationshipUpdate) => api.updateRelationship(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["relationships", projectId] });
      // History endpoint may also change if strength/type changed
      qc.invalidateQueries({ queryKey: ["relationship-history"] });
    },
  });
}

export function useDeleteRelationship(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deleteRelationship(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["relationships", projectId] }),
  });
}

export function useSoftCloseRelationship(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, validToChapter }: { id: number; validToChapter: number }) =>
      api.softCloseRelationship(id, validToChapter),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["relationships", projectId] });
      qc.invalidateQueries({ queryKey: ["relationship-history"] });
    },
  });
}

// === M3c-C: Events ===

export function useEvents(
  projectId: number,
  opts?: { chapterId?: number; filter?: EventFilter },
) {
  return useQuery({
    queryKey: ["events", projectId, opts?.chapterId, opts?.filter ?? "all"],
    queryFn: () => api.listEvents(projectId, opts),
  });
}

export function useCreateEvent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: EventCreate) => api.createEvent(data),
    onSuccess: (data) =>
      qc.invalidateQueries({ queryKey: ["events", data.project_id] }),
  });
}

export function useUpdateEvent(id: number, projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: EventUpdate) => api.updateEvent(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["events", projectId] }),
  });
}

export function useDeleteEvent(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deleteEvent(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["events", projectId] }),
  });
}

// === M3c-D: Plot Lines ===

export function usePlotLines(projectId: number, status?: PlotLineStatus) {
  return useQuery({
    queryKey: ["plot-lines", projectId, status],
    queryFn: () => api.listPlotLines(projectId, status),
  });
}

export function useCreatePlotLine() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: PlotLineCreate) => api.createPlotLine(data),
    onSuccess: (data) => qc.invalidateQueries({ queryKey: ["plot-lines", data.project_id] }),
  });
}

export function useUpdatePlotLine(id: number, projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: PlotLineUpdate) => api.updatePlotLine(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["plot-lines", projectId] }),
  });
}

export function useDeletePlotLine(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deletePlotLine(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["plot-lines", projectId] }),
  });
}
