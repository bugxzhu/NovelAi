import { test, expect } from "@playwright/test";

test("create project, navigate to chapters, create chapter", async ({ page }) => {
  await page.goto("/");
  await page.click("text=+ 新建项目");
  await page.fill('input[placeholder="给你的故事起个名字"]', "E2E 项目章节");
  await page.click("button:has-text('创建')");
  await page.waitForURL(/\/projects\/\d+\/chapters/);

  // Create chapter
  await page.click("text=+ 新建");
  await page.waitForURL(/\/chapters\/\d+/);

  // Editor visible
  await expect(page.locator(".ProseMirror")).toBeVisible();

  // Type content
  await page.locator(".ProseMirror").click();
  await page.keyboard.type("测试章节内容");
  await page.locator(".ProseMirror").blur();

  // Wait for autosave
  await page.waitForTimeout(700);

  // Reload to verify persistence
  await page.reload();
  await expect(page.locator(".ProseMirror")).toContainText("测试章节内容");
});
