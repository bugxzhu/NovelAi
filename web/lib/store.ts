import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

export type ActiveView = "chapters" | "characters" | "lore" | "history" | "search";
export type GenerationStatus = "idle" | "preparing" | "streaming" | "done" | "error";

interface UIState {
  // Layout (persisted)
  sidePanelWidth: number;
  contextPanelWidth: number;
  bottomPanelHeight: number;
  bottomPanelOpen: boolean;

  // Ephemeral (NOT persisted)
  activeView: ActiveView;
  generationStatus: GenerationStatus;

  // Actions
  setSidePanelWidth: (w: number) => void;
  setContextPanelWidth: (w: number) => void;
  setBottomPanelHeight: (h: number) => void;
  toggleBottomPanel: () => void;
  setBottomPanelOpen: (open: boolean) => void;
  setActiveView: (v: ActiveView) => void;
  setGenerationStatus: (s: GenerationStatus) => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      sidePanelWidth: 220,
      contextPanelWidth: 240,
      bottomPanelHeight: 200,
      bottomPanelOpen: false,
      activeView: "chapters",
      generationStatus: "idle",

      setSidePanelWidth: (w) => set({ sidePanelWidth: w }),
      setContextPanelWidth: (w) => set({ contextPanelWidth: w }),
      setBottomPanelHeight: (h) => set({ bottomPanelHeight: h }),
      toggleBottomPanel: () => set((s) => ({ bottomPanelOpen: !s.bottomPanelOpen })),
      setBottomPanelOpen: (open) => set({ bottomPanelOpen: open }),
      setActiveView: (v) => set({ activeView: v }),
      setGenerationStatus: (s) => set({ generationStatus: s }),
    }),
    {
      name: "m2b-ui",
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({
        sidePanelWidth: s.sidePanelWidth,
        contextPanelWidth: s.contextPanelWidth,
        bottomPanelHeight: s.bottomPanelHeight,
        bottomPanelOpen: s.bottomPanelOpen,
      }),
    }
  )
);

// Separate non-persistent store for generate params (resets each chapter entry)
interface GenerateParamsState {
  involvedCharacterIds: number[];
  locationId: number | null;
  setParams: (p: Partial<Omit<GenerateParamsState, "setParams" | "hydrateFromChapter" | "reset">>) => void;
  hydrateFromChapter: (chapter: {
    last_involved_character_ids: number[];
    last_location_id: number | null;
  }) => void;
  reset: () => void;
}

export const useGenerateParams = create<GenerateParamsState>((set) => ({
  involvedCharacterIds: [],
  locationId: null,
  setParams: (p) => set(p),
  hydrateFromChapter: (chapter) =>
    set({
      involvedCharacterIds: [...(chapter.last_involved_character_ids ?? [])],
      locationId: chapter.last_location_id ?? null,
    }),
  reset: () => set({ involvedCharacterIds: [], locationId: null }),
}));

// Per-chapter generation state, keyed by chapterId so multiple consumers
// (GenerateForm, StreamView) with the same chapterId share state.
export interface ChapterGenerationState {
  events: import("./sse").GenerationEvent[];
  generatedText: string;
  status: GenerationStatus;
  error: string | null;
}

interface GenerationStore {
  chapters: Record<number, ChapterGenerationState>;
  getChapter: (id: number) => ChapterGenerationState;
  setChapter: (
    id: number,
    patch:
      | Partial<ChapterGenerationState>
      | ((prev: ChapterGenerationState) => Partial<ChapterGenerationState>)
  ) => void;
  resetChapter: (id: number) => void;
}

export const DEFAULT_CHAPTER_STATE: ChapterGenerationState = {
  events: [],
  generatedText: "",
  status: "idle",
  error: null,
};

export const useGenerationStore = create<GenerationStore>((set, get) => ({
  chapters: {},
  getChapter: (id) => get().chapters[id] ?? DEFAULT_CHAPTER_STATE,
  setChapter: (id, patch) =>
    set((s) => {
      const current = s.chapters[id] ?? DEFAULT_CHAPTER_STATE;
      const resolved =
        typeof patch === "function" ? patch(current) : patch;
      return {
        chapters: {
          ...s.chapters,
          [id]: { ...current, ...resolved },
        },
      };
    }),
  resetChapter: (id) =>
    set((s) => ({ chapters: { ...s.chapters, [id]: DEFAULT_CHAPTER_STATE } })),
}));
