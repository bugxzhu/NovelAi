import { describe, it, expect, beforeEach } from "vitest";
import { useUIStore, useGenerateParams } from "@/lib/store";

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
