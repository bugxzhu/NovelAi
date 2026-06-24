import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { Issue, DiscussResponse, PolishResponse } from "./types";

export type ActiveView = "chapters" | "characters" | "lore" | "history" | "search";
export type GenerationStatus = "idle" | "preparing" | "streaming" | "done" | "error";
export type Theme = "light" | "dark";

interface UIState {
  // Layout (persisted)
  sidePanelWidth: number;
  contextPanelWidth: number;
  bottomPanelHeight: number;
  bottomPanelOpen: boolean;
  contextPanelOpen: boolean;

  // Theme (persisted)
  theme: Theme;

  // Ephemeral (NOT persisted)
  activeView: ActiveView;
  generationStatus: GenerationStatus;

  // Actions
  setSidePanelWidth: (w: number) => void;
  setContextPanelWidth: (w: number) => void;
  setBottomPanelHeight: (h: number) => void;
  toggleBottomPanel: () => void;
  setBottomPanelOpen: (open: boolean) => void;
  toggleContextPanel: () => void;
  setActiveView: (v: ActiveView) => void;
  setGenerationStatus: (s: GenerationStatus) => void;
  setTheme: (t: Theme) => void;
  toggleTheme: () => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      sidePanelWidth: 220,
      contextPanelWidth: 240,
      bottomPanelHeight: 200,
      bottomPanelOpen: false,
      contextPanelOpen: true,
      // Default to dark since the original spec was VS Code dark.
      theme: "dark",
      activeView: "chapters",
      generationStatus: "idle",

      setSidePanelWidth: (w) => set({ sidePanelWidth: w }),
      setContextPanelWidth: (w) => set({ contextPanelWidth: w }),
      setBottomPanelHeight: (h) => set({ bottomPanelHeight: h }),
      toggleBottomPanel: () => set((s) => ({ bottomPanelOpen: !s.bottomPanelOpen })),
      setBottomPanelOpen: (open) => set({ bottomPanelOpen: open }),
      toggleContextPanel: () => set((s) => ({ contextPanelOpen: !s.contextPanelOpen })),
      setActiveView: (v) => set({ activeView: v }),
      setGenerationStatus: (s) => set({ generationStatus: s }),
      setTheme: (t) => set({ theme: t }),
      toggleTheme: () =>
        set((s) => ({ theme: s.theme === "dark" ? "light" : "dark" })),
    }),
    {
      name: "m2b-ui",
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({
        sidePanelWidth: s.sidePanelWidth,
        contextPanelWidth: s.contextPanelWidth,
        bottomPanelHeight: s.bottomPanelHeight,
        bottomPanelOpen: s.bottomPanelOpen,
        contextPanelOpen: s.contextPanelOpen,
        theme: s.theme,
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

// Per-chapter beat/instruction draft. Survives route changes (component
// unmount/remount when switching tabs) within a session; cleared on Accept so
// the user starts fresh for the next generation. Not persisted to localStorage
// (refresh clears it — acceptable for a drafting UX).
export interface ChapterBeatDraft {
  beatText: string;
  instruction: string;
}

interface BeatDraftStore {
  chapters: Record<number, ChapterBeatDraft>;
  getDraft: (id: number) => ChapterBeatDraft;
  setBeatText: (id: number, text: string) => void;
  setInstruction: (id: number, text: string) => void;
  clear: (id: number) => void;
}

const DEFAULT_BEAT_DRAFT: ChapterBeatDraft = { beatText: "", instruction: "" };

export const useBeatDraftStore = create<BeatDraftStore>((set, get) => ({
  chapters: {},
  getDraft: (id) => get().chapters[id] ?? DEFAULT_BEAT_DRAFT,
  setBeatText: (id, text) =>
    set((s) => ({
      chapters: {
        ...s.chapters,
        [id]: { ...(s.chapters[id] ?? DEFAULT_BEAT_DRAFT), beatText: text },
      },
    })),
  setInstruction: (id, text) =>
    set((s) => ({
      chapters: {
        ...s.chapters,
        [id]: { ...(s.chapters[id] ?? DEFAULT_BEAT_DRAFT), instruction: text },
      },
    })),
  clear: (id) =>
    set((s) => ({
      chapters: { ...s.chapters, [id]: { ...DEFAULT_BEAT_DRAFT } },
    })),
}));

// === M4a: Review ===
// Issues are NOT persisted (每次启动从头开始). Tied to current session only.
interface ReviewState {
  issuesByChapter: Record<number, Issue[]>;
  modalOpenFor: number | null;
  setIssues: (chapterId: number, issues: Issue[]) => void;
  openModal: (chapterId: number) => void;
  closeModal: () => void;
  clearIssues: (chapterId: number) => void;
}

export const useReviewStore = create<ReviewState>((set) => ({
  issuesByChapter: {},
  modalOpenFor: null,
  setIssues: (chapterId, issues) =>
    set((s) => ({
      issuesByChapter: { ...s.issuesByChapter, [chapterId]: issues },
      modalOpenFor: chapterId, // auto-open modal on set
    })),
  openModal: (chapterId) => set({ modalOpenFor: chapterId }),
  closeModal: () => set({ modalOpenFor: null }),
  clearIssues: (chapterId) =>
    set((s) => {
      const next = { ...s.issuesByChapter };
      delete next[chapterId];
      return {
        issuesByChapter: next,
        modalOpenFor: s.modalOpenFor === chapterId ? null : s.modalOpenFor,
      };
    }),
}));

// === M4b-2: Discuss ===
// Discuss results are NOT persisted (ephemeral, per-session). Tied to current session only.
const EMPTY_DISCUSS: DiscussResponse | null = null;

interface DiscussState {
  resultByChapter: Record<number, DiscussResponse | null>;
  modalOpenFor: number | null;
  selectedText: string;
  setResult: (chapterId: number, result: DiscussResponse) => void;
  closeModal: () => void;
  clearResult: (chapterId: number) => void;
}

export const useDiscussStore = create<DiscussState>((set) => ({
  resultByChapter: {},
  modalOpenFor: null,
  selectedText: "",
  setResult: (chapterId, result) =>
    set((s) => ({
      resultByChapter: { ...s.resultByChapter, [chapterId]: result },
      modalOpenFor: chapterId,
    })),
  closeModal: () => set({ modalOpenFor: null }),
  clearResult: (chapterId) =>
    set((s) => {
      const next = { ...s.resultByChapter };
      delete next[chapterId];
      return {
        resultByChapter: next,
        modalOpenFor: s.modalOpenFor === chapterId ? null : s.modalOpenFor,
      };
    }),
}));

// Re-export the EMPTY constant for consumers that need a stable null reference.
// (Mirrors the EMPTY_* pattern used elsewhere to avoid selector snapshot churn.)
export { EMPTY_DISCUSS };

// === Polish ===
// Polish flow: PolishButton only OPENS the modal (no API call) — like Discuss,
// polish now takes a user direction input before the LLM call. The button
// captures the editor's selection range (from/to) at click time so the modal
// can replace that exact range on Accept. For whole-chapter polish (no
// selection), Accept calls editor.commands.setContent(polishedTexts[i]).
//
// All fields prefixed with "polish" to avoid collisions with other stores
// (Discuss uses `selectedText`, Review uses `modalOpen`).
interface PolishState {
  polishResult: PolishResponse | null;
  polishModalOpen: boolean;
  polishSelectedText: string;
  // ProseMirror positions for the selection captured at click time. Null when
  // the polish was whole-chapter (no selection) OR before any click.
  polishSelectionFrom: number | null;
  polishSelectionTo: number | null;
  setPolishOpen: (open: boolean) => void;
  setPolishResult: (result: PolishResponse) => void;
  closePolishModal: () => void;
}

export const usePolishStore = create<PolishState>((set) => ({
  polishResult: null,
  polishModalOpen: false,
  polishSelectedText: "",
  polishSelectionFrom: null,
  polishSelectionTo: null,
  setPolishOpen: (open) => set({ polishModalOpen: open, polishResult: null }),
  setPolishResult: (result) => set({ polishResult: result }),
  closePolishModal: () =>
    set({
      polishResult: null,
      polishModalOpen: false,
      polishSelectedText: "",
      polishSelectionFrom: null,
      polishSelectionTo: null,
    }),
}));
