import { test, expect } from "@playwright/test";
import type { Event } from "@/lib/types";

test("finalize event → accept → see in events list → can open foreshadow panel", async ({ page, request }) => {
  const base = "http://127.0.0.1:8005";

  // 1. Seed project + character + chapter via real backend
  const project = await request.post(`${base}/api/projects`, {
    data: { title: "E2E M3c-C" },
  }).then((r) => r.json());
  const pid = project.id;
  await request.post(`${base}/api/characters`, {
    data: { project_id: pid, name: "李雷" },
  });

  const chapter = await request.post(`${base}/api/chapters`, {
    data: {
      project_id: pid, order_index: 1, title: "残月重逢",
      content: "李雷在残月酒馆与韩梅重逢，气氛紧张。",
    },
  }).then((r) => r.json());
  const chId = chapter.id;

  // 2. Mock finalize (no real LLM call)
  await page.route(`**/api/chapters/${chId}/finalize`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        chapter_id: chId, summary: "x", pending_created: 1, log_id: 999,
      }),
    });
  });

  // 3. Mock pending list with one events pending
  await page.route(`**/api/pending-updates*`, (route) => {
    if (route.request().method() !== "GET") return route.continue();
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: 50, project_id: pid, chapter_id: chId,
          update_type: "hard_fact", operation: "create",
          target_table: "events", target_id: null,
          reason: "", status: "pending",
          entity_name: "残月酒馆重逢",
          entity_type: "", field_name: "", old_value: "",
          proposed_value: "李雷与韩梅在残月酒馆重逢",
          created_at: "2026-06-21T10:00:00Z",
          updated_at: "2026-06-21T10:00:00Z",
        },
      ]),
    });
  });

  // 4. Mock accept
  await page.route(`**/api/pending-updates/50/accept`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: 50, project_id: pid, chapter_id: chId,
        update_type: "hard_fact", operation: "create",
        target_table: "events", target_id: null,
        reason: "", status: "accepted",
        entity_name: "残月酒馆重逢",
        entity_type: "", field_name: "", old_value: "",
        proposed_value: "李雷与韩梅在残月酒馆重逢",
        created_at: "2026-06-21T10:00:00Z",
        updated_at: "2026-06-21T10:01:00Z",
      }),
    });
  });

  // 5. Mock events list with 2 events (one accepted + one for foreshadow target).
  // Stateful: after PATCH adds a foreshadow link, subsequent GET reflects the change.
  const event1: Event = {
    id: 1, project_id: pid, chapter_id: chId,
    chapter_title: "残月重逢", chapter_order: 1,
    title: "残月酒馆重逢", description: "李雷与韩梅在残月酒馆重逢",
    involved_characters: [], involved_character_names: [],
    location_id: null, location_name: "", plot_line_id: null,
    foreshadows: [], payoff_of: [], payoff_of_titles: [],
    is_unpaid: false,
    extractor_log_id: null, pending_update_id: 50,
    created_at: "2026-06-21T10:01:00Z",
    updated_at: "2026-06-21T10:01:00Z",
  };
  const event2: Event = {
    id: 2, project_id: pid, chapter_id: chId,
    chapter_title: "残月重逢", chapter_order: 1,
    title: "真相揭露", description: "韩梅的真实身份暴露",
    involved_characters: [], involved_character_names: [],
    location_id: null, location_name: "", plot_line_id: null,
    foreshadows: [] as number[], payoff_of: [], payoff_of_titles: [],
    is_unpaid: false,
    extractor_log_id: null, pending_update_id: null,
    created_at: "2026-06-21T10:02:00Z",
    updated_at: "2026-06-21T10:02:00Z",
  };

  await page.route(`**/api/events?*`, (route) => {
    if (route.request().method() !== "GET") return route.continue();
    // Recompute is_unpaid + payoff_of based on current foreshadows state
    const events = [event1, event2];
    for (const e of events) {
      e.payoff_of = events
        .filter((other) => other.id !== e.id && (other.foreshadows || []).includes(e.id))
        .map((other) => other.id);
      e.payoff_of_titles = e.payoff_of.map((pid2) => events.find((x) => x.id === pid2)?.title || "");
      e.is_unpaid = (e.foreshadows?.length ?? 0) > 0 && (e.foreshadows || []).some(
        (tid) => !events.some((o) => o.id !== e.id && (o.foreshadows || []).includes(tid))
      );
    }
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(events),
    });
  });

  // Mock PATCH on event 2 to add foreshadow link
  await page.route(`**/api/events/2`, (route) => {
    if (route.request().method() !== "PATCH") return route.continue();
    const body = JSON.parse(route.request().postData() || "{}");
    if (body.foreshadows) {
      event2.foreshadows = body.foreshadows;
    }
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ...event2, payoff_of: [], payoff_of_titles: [] }),
    });
  });

  // 6. Navigate to /pending → see event card → accept
  await page.goto(`/projects/${pid}/pending`);
  await expect(page.getByRole("main").getByText(/🎯/)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(/新事件 · 残月酒馆重逢/)).toBeVisible();
  await page.getByRole("button", { name: /接受/ }).first().click();
  await expect(page.getByText(/已接受/)).toBeVisible({ timeout: 10_000 });

  // 7. Navigate to /events → switch to 列表 tab → see both events, no ⚠️ yet
  // (filter tab text contains ⚠️, so we scope to event list buttons that start with 🎯)
  await page.goto(`/projects/${pid}/events`);
  await page.click("button:has-text('列表')");
  await expect(page.getByText(/🎯 残月酒馆重逢/)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(/🎯 真相揭露/)).toBeVisible();
  // No event button should show ⚠️ yet
  const eventButtons = page.locator("button", { hasText: /^⚠️ 🎯/ });
  await expect(eventButtons).toHaveCount(0);

  // 8. Click 真相揭露 → form + foreshadow panel
  await page.getByText(/🎯 真相揭露/).first().click();
  await expect(page.getByText(/伏笔链接/)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(/此事件是以下事件的伏笔/)).toBeVisible();
  await expect(page.getByText(/此事件兑现了以下伏笔/)).toBeVisible();

  // 9. Click "+ 添加目标事件" → select 残月酒馆重逢 (label format: "第 N 章 · title")
  await page.getByRole("button", { name: /添加目标事件/ }).click();
  await page.locator("select").last().selectOption({ label: "第 1 章 · 残月酒馆重逢" });

  // 10. List refreshes via invalidation; 真相揭露 now foreshadows 残月酒馆重逢 → is_unpaid=true → ⚠️ appears
  await expect(page.getByText(/🎯 真相揭露/).first()).toBeVisible({ timeout: 10_000 });
  // Exactly one event button should now show ⚠️ (真相揭露)
  const unpaidButtons = page.locator("button", { hasText: /^⚠️ 🎯/ });
  await expect(unpaidButtons).toHaveCount(1);
  await expect(unpaidButtons.first()).toContainText(/真相揭露/);
});
