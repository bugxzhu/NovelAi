# NovelAI M3d — 否定记忆（Negative Memory）设计文档

- **日期**：2026-06-21
- **状态**：草案（待用户审阅）
- **范围**：M3d = Extractor 在抽取时查询项目内已拒绝的 pending_updates，注入 prompt 提示"以下已被拒绝，不要重复抽取"
- **依赖**：M3a（Extractor + pending_updates）、M3c-A/B/C（characters/lore/states/relationships/events accept/reject）

---

## 1. 目标与非目标

### 1.1 目标

让 Extractor 在重新抽取时"记住"用户已拒绝的建议，减少重复抽错：

1. `extract_chapter` 在渲染 prompt 前查询项目内所有 `status='rejected'` 的 pending_updates
2. 按 target_table 格式化为人类可读的 entity_description
3. 注入 `extractor/user.j2` 的"已拒绝（不要重复抽取）"段
4. LLM 看到列表后避免重新建议相同内容

### 1.2 非目标

- 否定记忆的 UI 管理（不单独做"查看/删除否定记忆"页面）
- 按 chapter 上下文过滤否定记忆（全部项目级）
- 否定记忆的 TTL / 自动过期（永久保留直到用户不 re-finalize 时自然清理）
- 前端改动（纯后端 prompt 增强）

### 1.3 关键决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 查询范围 | 全部 `status='rejected'` pending_updates | 单用户单机 <100 条；token 影响小 |
| 格式 | 按 target_table 格式化 entity_description + decision_note | LLM 一目了然"什么被拒绝了/为什么" |
| 新表/新 API | 无 | 复用现有 PendingUpdate + extract_chapter |
| Prompt 位置 | user.j2 "已有实体"段之后 | LLM 先看到"已有"再看"已拒绝"——双重去重 |

---

## 2. 实现

### 2.1 `extract_chapter` 改动

在 `app/agents/extractor.py` 的 `extract_chapter` 函数中，在渲染 `user_prompt` 之前，查询已拒绝的 pendings 并格式化：

```python
rejected_pendings = list(db.scalars(
    select(PendingUpdate).where(
        PendingUpdate.project_id == chapter.project_id,
        PendingUpdate.status == "rejected",
    ).order_by(PendingUpdate.id.desc()).limit(100)
))

rejected_suggestions = []
for rp in rejected_pendings:
    pc = rp.proposed_change or {}
    desc = ""
    if rp.target_table == "characters":
        name = pc.get("name", "")
        role = pc.get("role", "")
        desc = f"人物：{name}（{role}）" if name else ""
    elif rp.target_table == "lore_entries":
        name = pc.get("name", "")
        ltype = pc.get("type", "")
        desc = f"设定：{name}（{ltype}）" if name else ""
    elif rp.target_table == "character_states":
        name = pc.get("character_name", "")
        snapshot = pc.get("state_snapshot", "")
        desc = f"状态变化：{name} → {snapshot}" if name else ""
    elif rp.target_table == "relationships":
        from_name = pc.get("from_character_name", "")
        to_name = pc.get("to_character_name", "")
        rtype = pc.get("type", "")
        desc = f"关系：{from_name} → {to_name} {rtype}" if from_name else ""
    elif rp.target_table == "events":
        title = pc.get("title", "")
        desc = f"事件：{title}" if title else ""
    if desc:
        rejected_suggestions.append({
            "entity_description": desc,
            "note": rp.decision_note or "",
        })
```

然后传给 user.j2:

```python
    user_prompt = render(
        "extractor/user.j2",
        project=project,
        chapter=chapter,
        existing_characters=existing_characters,
        existing_lore=existing_lore,
        existing_relationships=existing_relationships_view,
        rejected_suggestions=rejected_suggestions,
    )
```

### 2.2 `extractor/user.j2` 改动

在"已有关系"段之后、"请抽取..."之前，插入：

```
{% if rejected_suggestions %}
# 已拒绝的抽取建议（不要重复抽取）

以下建议已被用户拒绝，不要在本章重复抽取相同内容：
{% for r in rejected_suggestions %}
- {{ r.entity_description }}{% if r.note %} — 原因：{{ r.note }}{% endif %}
{% endfor %}
{% endif %}
```

### 2.3 无新表 / 无新 API

- 复用 `PendingUpdate` 表（已有 `status='rejected'` + `decision_note`）
- 复用 `extract_chapter` 函数（加查询逻辑）
- 复用 `extractor/user.j2`（加渲染段）
- 无前端改动

---

## 3. 测试

| 测试 | 验证 |
|---|---|
| `test_extract_prompt_includes_rejected_suggestions` | user.j2 渲染含"已拒绝"段 + entity_description |
| `test_extract_prompt_empty_rejected` | 无拒绝时省略"已拒绝"段 |
| `test_extract_chapter_queries_rejected` | extract_chapter 传 rejected_suggestions 给 render |
| `test_render_extractor_user_rejected_all_types` | 5 种 target_table 都正确格式化 |

---

## 4. 验收清单

| # | 验收项 |
|---|---|
| 1 | extract_chapter 查询项目内 rejected pendings |
| 2 | user.j2 渲染"已拒绝"段（仅有拒绝时） |
| 3 | 5 种 target_table 都正确格式化 |
| 4 | 全后端测试通过 |

---

## 5. 未来扩展

- 否定记忆 TTL（3 个月后自动清除）
- 按 chapter 过滤（只看最近 N 章的拒绝）
- UI 管理（"否定记忆"面板查看/删除）
