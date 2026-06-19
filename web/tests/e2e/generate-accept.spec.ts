import { test, expect } from "@playwright/test";

test("generate and accept inserts into editor", async ({ page }) => {
  test.setTimeout(60_000);
  // Setup: create project via UI
  await page.goto("/");
  await page.click("text=+ 新建项目");
  await page.waitForURL(/\/projects\/\d+\/chapters/);

  const projectId = new URL(page.url()).pathname.split("/")[2];

  // Seed character + chapter via API
  await fetch(`http://127.0.0.1:8005/api/characters`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: Number(projectId), name: "测试人物" }),
  });

  const ch = await fetch(`http://127.0.0.1:8005/api/chapters`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: Number(projectId), order_index: 1, title: "测试章节" }),
  }).then((r) => r.json());

  // Mock SSE response — replace :id with actual chapter id
  const sseBody = [
    `event: meta\ndata: {"generation_log_id":1,"model":"m","model_task":"writer_long","chapter_id":${ch.id},"started_at":"s"}\n\n`,
    `event: context\ndata: {"context_bundle":{"project":{"id":1,"title":"","genre":"","main_theme":"","tone":"","premise":""},"world_overview":null,"characters":[],"relationships":[],"faction_lore":[],"location_lore":[],"recent_chapter_summaries":[]}}\n\n`,
    `event: token\ndata: {"text":"夜色压在屋脊上"}\n\n`,
    `event: token\ndata: {"text":"，残月酒馆的灯还亮着。"}\n\n`,
    `event: done\ndata: {"generation_log_id":1,"input_tokens":10,"output_tokens":12,"stop_reason":"end_turn"}\n\n`,
  ].join("");
  await page.route(`**/api/chapters/${ch.id}/generate`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: sseBody,
    });
  });

  // Clear any persisted UI state so the bottom panel starts collapsed
  await page.goto("/");
  await page.evaluate(() => localStorage.removeItem("m2b-ui"));

  await page.goto(`/projects/${projectId}/chapters/${ch.id}`);
  // Wait for editor to be ready (chapter loaded)
  await expect(page.locator(".ProseMirror")).toBeVisible({ timeout: 30_000 });

  // Open bottom panel
  await page.click("text=⚡ 生成（展开）");

  // Fill beat (first textarea in GenerateForm, identified by placeholder)
  const beatTextarea = page.locator('textarea[placeholder*="残月酒馆"]').first();
  await expect(beatTextarea).toBeVisible({ timeout: 10_000 });
  await beatTextarea.fill("主角推开酒馆的门");

  // Character chip renders "{name}（{role}）" — use substring match
  await page.locator("button", { hasText: "测试人物" }).click();

  // Submit
  await page.click("button:has-text('✨ 生成')");

  // Wait for done event
  await expect(page.locator("text=✓ 完成")).toBeVisible({ timeout: 5_000 });

  // Accept
  await page.click("button:has-text('✓ 接受并插入')");

  // Verify editor has content
  await expect(page.locator(".ProseMirror")).toContainText("夜色压在屋脊上");
});
