import { test, expect } from "@playwright/test";

test("finalize produces state_changes pending → accept → see in character timeline", async ({ page, request }) => {
  const base = "http://127.0.0.1:8005";

  // 1. Seed project + character + chapter via API
  const project = await request.post(`${base}/api/projects`, {
    data: { title: "E2E M3c-B" },
  }).then((r) => r.json());
  const pid = project.id;

  const char = await request.post(`${base}/api/characters`, {
    data: { project_id: pid, name: "李雷", current_state: "警惕" },
  }).then((r) => r.json());
  const cid = char.id;

  const chapter = await request.post(`${base}/api/chapters`, {
    data: {
      project_id: pid,
      order_index: 1,
      title: "伏击",
      content: "李雷被韩梅伏击受伤，左臂中刀。他决心复仇。",
    },
  }).then((r) => r.json());
  const chId = chapter.id;

  // 2. Mock finalize response with a state_changes entry
  await page.route(`**/api/chapters/${chId}/finalize`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        chapter_id: chId,
        summary: "李雷被伏击。",
        pending_created: 1,
        log_id: 999,
      }),
    });
  });

  // 3. Mock pending list to include a state_changes entry
  await page.route(`**/api/pending-updates*`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: 50,
          project_id: pid,
          chapter_id: chId,
          update_type: "soft_fact",
          operation: "create",
          target_table: "character_states",
          target_id: null,
          reason: "chapter_id=1 状态变化",
          status: "pending",
          entity_name: "李雷",
          entity_type: "",
          field_name: "state_snapshot",
          old_value: "",
          proposed_value: "愤怒且受伤；决心复仇",
          created_at: "2026-06-20T14:00:00Z",
          updated_at: "2026-06-20T14:00:00Z",
        },
      ]),
    });
  });

  // 4. Mock accept → returns accepted status
  await page.route(`**/api/pending-updates/50/accept`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: 50,
        project_id: pid,
        chapter_id: chId,
        update_type: "soft_fact",
        operation: "create",
        target_table: "character_states",
        target_id: null,
        reason: "chapter_id=1 状态变化",
        status: "accepted",
        entity_name: "李雷",
        entity_type: "",
        field_name: "state_snapshot",
        old_value: "",
        proposed_value: "愤怒且受伤；决心复仇",
        created_at: "2026-06-20T14:00:00Z",
        updated_at: "2026-06-20T14:01:00Z",
      }),
    });
  });

  // 5. Mock character-states endpoint to return the accepted state
  await page.route(`**/api/characters/${cid}/states*`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: 1,
          character_id: cid,
          chapter_id: chId,
          chapter_title: "伏击",
          chapter_order: 1,
          state_snapshot: "愤怒且受伤；决心复仇",
          change_summary: "被伏击",
          extractor_log_id: 999,
          pending_update_id: 50,
          created_at: "2026-06-20T14:01:00Z",
          updated_at: "2026-06-20T14:01:00Z",
        },
      ]),
    });
  });

  // 6. Mock character detail + list to show mirrored current_state
  await page.route(`**/api/characters/${cid}`, (route) => {
    if (route.request().method() !== "GET") {
      return route.continue();
    }
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ...char,
        current_state: "愤怒且受伤；决心复仇",
      }),
    });
  });

  await page.route(`**/api/characters?*`, (route) => {
    if (route.request().method() !== "GET") return route.continue();
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        { ...char, current_state: "愤怒且受伤；决心复仇" },
      ]),
    });
  });

  // 7. Navigate to pending page → accept state_changes pending
  await page.goto(`/projects/${pid}/pending`);
  await expect(page.getByText(/状态变化 · 李雷/)).toBeVisible({ timeout: 10_000 });
  await page.getByRole("button", { name: /接受/ }).first().click();
  await expect(page.getByText(/已接受/)).toBeVisible({ timeout: 10_000 });

  // 8. Navigate to characters page → open character → expand timeline
  await page.goto(`/projects/${pid}/characters`);
  await page.getByRole("button", { name: /李雷/ }).first().click();
  await page.getByRole("button", { name: /状态轨迹/ }).click();

  // 9. Verify timeline shows the state
  await expect(page.getByText(/第 1 章 · 伏击/)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(/愤怒且受伤；决心复仇/)).toBeVisible();
});
