import { describe, it, expect, beforeEach } from "vitest";
import { useUIStore, useGenerateParams, useGenerationStore } from "@/lib/store";

beforeEach(() => {
  localStorage.clear();
  useUIStore.setState({
    sidePanelWidth: 220,
    contextPanelWidth: 240,
    bottomPanelHeight: 200,
    bottomPanelOpen: false,
    activeView: "chapters",
    generationStatus: "idle",
  });
  useGenerateParams.setState({
    involvedCharacterIds: [],
    locationId: null,
  });
  useGenerationStore.setState({ chapters: {} });
});

describe("useUIStore", () => {
  it("toggles bottomPanelOpen", () => {
    useUIStore.getState().toggleBottomPanel();
    expect(useUIStore.getState().bottomPanelOpen).toBe(true);
  });

  it("updates sidePanelWidth", () => {
    useUIStore.getState().setSidePanelWidth(300);
    expect(useUIStore.getState().sidePanelWidth).toBe(300);
  });

  it("partialize only persists layout fields", () => {
    useUIStore.setState({ generationStatus: "streaming", bottomPanelOpen: true });
    const persisted = JSON.parse(localStorage.getItem("m2b-ui") ?? "{}");
    expect(persisted.state).toMatchObject({
      sidePanelWidth: 220,
      bottomPanelOpen: true,
    });
    // generationStatus not persisted
    expect(persisted.state.generationStatus).toBeUndefined();
  });
});

describe("useGenerateParams", () => {
  it("sets involvedCharacterIds", () => {
    useGenerateParams.getState().setParams({ involvedCharacterIds: [1, 2] });
    expect(useGenerateParams.getState().involvedCharacterIds).toEqual([1, 2]);
  });

  it("setParams merges partial", () => {
    useGenerateParams.getState().setParams({ involvedCharacterIds: [1] });
    useGenerateParams.getState().setParams({ locationId: 7 });
    expect(useGenerateParams.getState()).toMatchObject({
      involvedCharacterIds: [1],
      locationId: 7,
    });
  });

  it("hydrateFromChapter resets params from chapter defaults", () => {
    useGenerateParams.getState().setParams({
      involvedCharacterIds: [99],
      locationId: 88,
    });
    useGenerateParams.getState().hydrateFromChapter({
      last_involved_character_ids: [3, 4],
      last_location_id: 9,
    });
    expect(useGenerateParams.getState()).toMatchObject({
      involvedCharacterIds: [3, 4],
      locationId: 9,
    });
  });
});

describe("useGenerationStore", () => {
  it("getChapter returns defaults for unknown id", () => {
    const s = useGenerationStore.getState().getChapter(42);
    expect(s).toEqual({
      events: [],
      generatedText: "",
      status: "idle",
      error: null,
    });
  });

  it("setChapter merges patch object", () => {
    useGenerationStore.getState().setChapter(1, { status: "preparing" });
    expect(useGenerationStore.getState().chapters[1].status).toBe("preparing");
    expect(useGenerationStore.getState().chapters[1].events).toEqual([]);
  });

  it("setChapter accepts updater function reading prev", () => {
    useGenerationStore.getState().setChapter(1, { events: [], generatedText: "" });
    useGenerationStore.getState().setChapter(1, (prev) => ({
      generatedText: prev.generatedText + "abc",
    }));
    useGenerationStore.getState().setChapter(1, (prev) => ({
      generatedText: prev.generatedText + "def",
    }));
    expect(useGenerationStore.getState().chapters[1].generatedText).toBe("abcdef");
  });

  it("different chapterIds are independent", () => {
    useGenerationStore.getState().setChapter(1, { status: "streaming" });
    useGenerationStore.getState().setChapter(2, { status: "done" });
    expect(useGenerationStore.getState().chapters[1].status).toBe("streaming");
    expect(useGenerationStore.getState().chapters[2].status).toBe("done");
  });

  it("resetChapter restores defaults", () => {
    useGenerationStore.getState().setChapter(1, {
      status: "error",
      error: "boom",
      events: [{ type: "token", text: "x" }] as never,
      generatedText: "x",
    });
    useGenerationStore.getState().resetChapter(1);
    expect(useGenerationStore.getState().chapters[1]).toEqual({
      events: [],
      generatedText: "",
      status: "idle",
      error: null,
    });
  });
});
