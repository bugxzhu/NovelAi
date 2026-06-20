import { test, expect } from "@playwright/test";

test("finalize produces relationship_changes pending → accept → see in history", async ({ page, request }) => {
  const base = "http://127.0.0.1:8005";

  // 1. Seed project + 2 characters + chapter via API (real backend, no mock)
  const project = await request.post(`${base}/api/projects`, {
    data: { title: "E2E M3c-A" },
  }).then((r) => r.json());
  const pid = project.id;

  const c1 = await request.post(`${base}/api/characters`, {
    data: { project_id: pid, name: "李雷" },
  }).then((r) => r.json());
  const c2 = await request.post(`${base}/api/characters`, {
    data: { project_id: pid, name: "韩梅" },
  }).then((r) => r.json());

  const chapter = await request.post(`${base}/api/chapters`, {
    data: {
      project_id: pid,
      order_index: 1,
      title: "伏击",
      content: "韩梅伏击李雷。",
    },
  }).then((r) => r.json());
  const chId = chapter.id;

  // 2. Mock finalize to return without actually calling LLM
  await page.route(`**/api/chapters/${chId}/finalize`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        chapter_id: chId,
        summary: "x",
        pending_created: 1,
        log_id: 999,
      }),
    });
  });

  // 3. Mock pending list to include a relationship_changes entry
  await page.route(`**/api/pending-updates*`, (route) => {
    if (route.request().method() !== "GET") {
      return route.continue();
    }
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
          target_table: "relationships",
          target_id: null,
          reason: "",
          status: "pending",
          entity_name: "李雷 → 韩梅",
          entity_type: "",
          field_name: "",
          old_value: "",
          proposed_value: "仇人（强度 -0.8）：决心复仇",
          created_at: "2026-06-20T14:00:00Z",
          updated_at: "2026-06-20T14:00:00Z",
        },
      ]),
    });
  });

  // 4. Mock accept endpoint
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
        target_table: "relationships",
        target_id: null,
        reason: "",
        status: "accepted",
        entity_name: "李雷 → 韩梅",
        entity_type: "",
        field_name: "",
        old_value: "",
        proposed_value: "仇人（强度 -0.8）：决心复仇",
        created_at: "2026-06-20T14:00:00Z",
        updated_at: "2026-06-20T14:01:00Z",
      }),
    });
  });

  // 5. Mock relationships list to show accepted version
  await page.route(`**/api/relationships?*`, (route) => {
    if (route.request().method() !== "GET") return route.continue();
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: 2,
          project_id: pid,
          from_char_id: c1.id,
          from_char_name: "李雷",
          to_char_id: c2.id,
          to_char_name: "韩梅",
          type: "仇人",
          strength: -0.8,
          description: "决心复仇",
          valid_from_chapter: chId,
          valid_to_chapter: null,
          change_summary: "伏击",
          extractor_log_id: null,
          pending_update_id: 50,
          created_at: "2026-06-20T14:01:00Z",
          updated_at: "2026-06-20T14:01:00Z",
        },
      ]),
    });
  });

  // 6. Mock history endpoint to show 1 version
  await page.route(`**/api/relationships/history*`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          version_id: 2,
          valid_from_chapter: chId,
          valid_to_chapter: null,
          type: "仇人",
          strength: -0.8,
          description: "决心复仇",
          change_summary: "伏击",
          created_at: "2026-06-20T14:01:00Z",
        },
      ]),
    });
  });

  // 7. Navigate to /pending → see relationship card → accept
  await page.goto(`/projects/${pid}/pending`);
  await expect(page.getByRole("main").getByText(/🤝/)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(/关系变化 · 李雷 → 韩梅/)).toBeVisible();
  await page.getByRole("button", { name: /接受/ }).first().click();
  await expect(page.getByText(/已接受/)).toBeVisible({ timeout: 10_000 });

  // 8. Navigate to /relationships → see 仇人 in list
  await page.goto(`/projects/${pid}/relationships`);
  await expect(page.getByText(/李雷 → 韩梅 · 仇人/)).toBeVisible({ timeout: 10_000 });

  // 9. Click relationship → history panel shows 1 version
  await page.getByText(/李雷 → 韩梅/).first().click();
  await expect(page.getByText(/演变历史（1 版本）/)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(/第 \d+ 章 → 当前/)).toBeVisible();
});
