import { test, expect } from "@playwright/test";

test("review → modal shows issues → close clears", async ({ page, request }) => {
  const base = "http://127.0.0.1:8005";

  // 1. Seed project + chapter via API
  const project = await request.post(`${base}/api/projects`, {
    data: { title: "E2E M4a" },
  }).then((r) => r.json());
  const pid = project.id;

  const chapter = await request.post(`${base}/api/chapters`, {
    data: {
      project_id: pid,
      order_index: 1,
      title: "第一章",
      content: "李雷推开了残月酒馆的门，看见了韩梅。",
    },
  }).then((r) => r.json());
  const chId = chapter.id;

  // 2. Mock review endpoint
  await page.route(`**/api/chapters/${chId}/review`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        chapter_id: chId,
        log_id: 999,
        issues: [
          {
            severity: "warn",
            category: "character",
            location: "李雷推开了残月酒馆的门",
            description: "李雷本章状态突变",
            suggestion: "补充心理转变",
          },
          {
            severity: "info",
            category: "plot",
            location: "",
            description: "整章节奏过快",
            suggestion: "",
          },
        ],
      }),
    });
  });

  // 3. Clear any persisted UI state (collapsed panel) before navigating
  await page.goto("/");
  await page.evaluate(() => localStorage.removeItem("m2b-ui"));

  // 4. Navigate to chapter editor
  await page.goto(`/projects/${pid}/chapters/${chId}`);
  await expect(page.locator(".ProseMirror")).toBeVisible({ timeout: 30_000 });

  // 5. Click review button
  await page.getByRole("button", { name: /🔍 审稿/ }).click();

  // 6. Wait for modal
  await expect(page.getByText(/审稿报告/)).toBeVisible({ timeout: 10_000 });

  // 7. Verify issues by category
  await expect(page.getByText(/人物一致性/)).toBeVisible();
  await expect(page.getByText(/情节矛盾/)).toBeVisible();
  await expect(page.getByText(/李雷本章状态突变/)).toBeVisible();
  await expect(page.getByText(/整章节奏过快/)).toBeVisible();

  // 8. Verify highlight applied in editor (mark element with data-issue-id)
  // The first issue has location "李雷推开了残月酒馆的门" which is in the chapter content.
  // The text offset → ProseMirror pos conversion is best-effort per spec §11.1;
  // if it misses, the modal assertions above are the primary UX signal.
  const highlightedMarks = page.locator("mark[data-issue-id]");
  await expect(highlightedMarks.first()).toBeVisible({ timeout: 5_000 });

  // 9. Close modal
  await page.getByRole("button", { name: /我知道了/ }).click();
  await expect(page.getByText(/审稿报告/)).toBeHidden();
});
