import { test, expect } from "@playwright/test";

test("manual snapshot → edit → restore round-trip", async ({ page, request }) => {
  const base = "http://127.0.0.1:8005";

  // Seed via API
  const proj = await request.post(`${base}/api/projects`, {
    data: { title: "E2E 版本测试" },
  }).then((r) => r.json());
  const pid = proj.id;

  const ch = await request.post(`${base}/api/chapters`, {
    data: { project_id: pid, order_index: 1, title: "版本测试章", content: "" },
  }).then((r) => r.json());
  const cid = ch.id;

  // Set up dialog handler BEFORE any click that triggers confirm()
  page.on("dialog", (d) => d.accept());

  // 1. Navigate to editor
  await page.goto(`/projects/${pid}/chapters/${cid}`);
  await expect(page.locator(".ProseMirror")).toBeVisible({ timeout: 10_000 });

  // 2. Type content
  await page.locator(".ProseMirror").click();
  await page.keyboard.type("原始内容 here");
  await page.locator(".ProseMirror").blur();
  await page.waitForTimeout(800); // autosave debounce + flush

  // 3. Click 💾 snapshot
  await page.click("button[title='存为版本（可从版本页恢复）']");
  await page.waitForTimeout(1000);

  // 4. Navigate to versions page via 📜
  await page.click("button[title='版本历史']");
  await page.waitForURL(/\/versions$/);

  // 5. Verify 1 version visible
  await expect(page.getByText("手动")).toBeVisible({ timeout: 5_000 });
  await expect(page.locator("pre")).toContainText("原始内容");

  // 6. Go back, edit more
  await page.goBack();
  await expect(page.locator(".ProseMirror")).toBeVisible({ timeout: 10_000 });
  await page.locator(".ProseMirror").click();
  await page.keyboard.type(" 加了一些新内容");
  await page.locator(".ProseMirror").blur();
  await page.waitForTimeout(800);

  // 7. Navigate to versions → restore the snapshot
  await page.click("button[title='版本历史']");
  await page.waitForURL(/\/versions$/);
  await page.click("button:has-text('⏩ 恢复此版本')");
  await page.waitForURL(/\/projects\/\d+\/chapters\/\d+$/, { timeout: 10_000 });
  await expect(page.locator(".ProseMirror")).toBeVisible({ timeout: 10_000 });

  // 8. Verify editor content is back to original (no "加了一些新内容")
  await expect(page.locator(".ProseMirror")).not.toContainText("加了一些新内容");
  await expect(page.locator(".ProseMirror")).toContainText("原始内容");
});
