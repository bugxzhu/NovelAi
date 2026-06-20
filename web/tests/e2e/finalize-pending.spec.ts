import { test, expect } from "@playwright/test";

test("finalize → see pending badge → visit pending page", async ({ page, request }) => {
  // 1. Create project + chapter with content via API
  const base = "http://127.0.0.1:8005";
  const project = await request.post(`${base}/api/projects`, {
    data: { title: "E2E Test" },
  }).then((r) => r.json());
  const pid = project.id;

  await request.post(`${base}/api/characters`, {
    data: { project_id: pid, name: "李雷", background: "old bg" },
  }).then((r) => r.json());

  const chapter = await request.post(`${base}/api/chapters`, {
    data: {
      project_id: pid,
      order_index: 1,
      title: "测试章节",
      content: "夜色压在屋脊上。李雷推开残月酒馆的门，看见了韩梅。韩梅是酒馆的老板娘，约三十岁。",
    },
  }).then((r) => r.json());
  const cid = chapter.id;

  // 2. Mock the finalize endpoint response
  await page.route(`**/api/chapters/${cid}/finalize`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        chapter_id: cid,
        summary: "李雷进入酒馆遇见韩梅。",
        pending_created: 2,
        log_id: 1,
      }),
    });
  });

  // 3. Visit chapter page and click Finalize
  await page.goto(`/projects/${pid}/chapters/${cid}`);
  await page.click("button:has-text('完成本章')");
  await expect(page.locator("text=已抽取 2 条新事实")).toBeVisible({ timeout: 5_000 });

  // 4. Go to pending page via ActivityBar (icon button uses title attribute)
  await page.getByTitle("待处理").click();
  await page.waitForURL(/\/pending$/);

  // 5. Page should load successfully (real backend extraction wasn't called,
  //    but we're verifying the UI navigation flow). SidePanel title shows 待处理.
  await expect(page.locator("text=待处理").first()).toBeVisible();
});
