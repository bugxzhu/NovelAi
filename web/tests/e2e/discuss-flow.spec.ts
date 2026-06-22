import { test, expect } from "@playwright/test";

test("discuss → 3 branches → recommended highlight → close", async ({ page, request }) => {
  const base = "http://127.0.0.1:8005";

  // 1. Seed project + chapter via API
  const project = await request.post(`${base}/api/projects`, {
    data: { title: "E2E M4b-2" },
  }).then((r) => r.json());
  const pid = project.id;

  const chapter = await request.post(`${base}/api/chapters`, {
    data: {
      project_id: pid,
      order_index: 1,
      title: "第一章",
      content: "李雷推开了残月酒馆的门。",
    },
  }).then((r) => r.json());
  const chId = chapter.id;

  // 2. Mock discuss endpoint — never hits the real LLM
  await page.route(`**/api/chapters/${chId}/discuss`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        question: "如果让李雷和韩梅和解？",
        branches: [
          { label: "A", title: "直接和解", summary: "走向A", conflicts: "冲突A",
            opportunities: "机会A", character_impact: "人物A" },
          { label: "B", title: "暗中布局", summary: "走向B", conflicts: "冲突B",
            opportunities: "机会B", character_impact: "人物B" },
          { label: "C", title: "拒绝和解", summary: "走向C", conflicts: "冲突C",
            opportunities: "机会C", character_impact: "人物C" },
        ],
        recommended: "B",
        reasoning: "B 分支在保持张力的同时给了人物成长空间。",
        log_id: 999,
      }),
    });
  });

  // 3. Clear any persisted UI state (collapsed panel) before navigating
  await page.goto("/");
  await page.evaluate(() => localStorage.removeItem("m2b-ui"));

  // 4. Navigate to chapter editor
  await page.goto(`/projects/${pid}/chapters/${chId}`);
  await expect(page.locator(".ProseMirror")).toBeVisible({ timeout: 30_000 });

  // 5. Click 💬 探讨 button
  await page.getByRole("button", { name: /探讨/ }).click();

  // 6. Wait for modal
  await expect(page.getByText(/情节探讨/)).toBeVisible({ timeout: 10_000 });

  // 7. Type question
  await page.getByPlaceholder(/如果/).fill("如果让李雷和韩梅和解？");

  // 8. Click 推演
  await page.getByRole("button", { name: /推演/ }).click();

  // 9. Wait for 3 branches
  await expect(page.getByText(/直接和解/)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(/暗中布局/)).toBeVisible();
  await expect(page.getByText(/拒绝和解/)).toBeVisible();

  // 10. Verify recommended highlight (B branch gets ✓ 推荐 badge)
  await expect(page.getByText(/✓ 推荐/)).toBeVisible();

  // 11. Close
  await page.getByRole("button", { name: /知道了/ }).click();
  await expect(page.getByText(/情节探讨/)).toBeHidden();
});
