import { describe, it, expectTypeOf } from "vitest";
import type {
  Project,
  Chapter,
  GenerateRequest,
  GenerationLogDetail,
} from "@/lib/types";

describe("types", () => {
  it("Chapter has last_involved_character_ids as number[]", () => {
    expectTypeOf<Chapter["last_involved_character_ids"]>().toEqualTypeOf<number[]>();
  });

  it("Chapter.last_location_id is number | null", () => {
    expectTypeOf<Chapter["last_location_id"]>().toEqualTypeOf<number | null>();
  });

  it("Project has required fields", () => {
    const p: Project = {
      id: 1, title: "x", genre: "", premise: "", main_theme: "", tone: "",
      created_at: "", updated_at: "",
    };
    expectTypeOf(p).toMatchTypeOf<Project>();
  });

  it("GenerateRequest allows optional fields", () => {
    const r: GenerateRequest = {
      beat_text: "x",
      involved_character_ids: [1],
    };
    expectTypeOf(r).toMatchTypeOf<GenerateRequest>();
  });

  it("GenerationLogDetail has prompt fields", () => {
    expectTypeOf<GenerationLogDetail>().toHaveProperty("system_prompt").toBeString();
    expectTypeOf<GenerationLogDetail>().toHaveProperty("user_prompt").toBeString();
  });
});
