import { test, expect } from "@playwright/test";

test("invalid context returns 422 from backend", async ({ page }) => {
  await page.goto("/");
  await page.click("text=+ 新建项目");
  await page.fill('input[placeholder="给你的故事起个名字"]', "E2E 跨项目校验");
  await page.click("button:has-text('创建')");
  await page.waitForURL(/\/projects\/\d+\/chapters/);

  const projectId = new URL(page.url()).pathname.split("/")[2];

  const ch = await fetch(`http://127.0.0.1:8005/api/chapters`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: Number(projectId), order_index: 1, title: "x" }),
  }).then((r) => r.json());

  // Create character in ANOTHER project
  const otherProject = await fetch(`http://127.0.0.1:8005/api/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: "Other" }),
  }).then((r) => r.json());
  const otherChar = await fetch(`http://127.0.0.1:8005/api/characters`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: otherProject.id, name: "外项目人物" }),
  }).then((r) => r.json());

  // Direct API call to verify backend rejects cross-project character
  const r = await fetch(`http://127.0.0.1:8005/api/chapters/${ch.id}/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      beat_text: "x",
      involved_character_ids: [otherChar.id],
    }),
  });
  expect(r.status).toBe(422);
  const body = await r.json();
  expect(body.detail.error).toBe("invalid_context");
  expect(body.detail.invalid_character_ids).toContain(otherChar.id);
});
