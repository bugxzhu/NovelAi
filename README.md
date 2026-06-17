# NovelAI

AI 辅助小说写作工具（本地优先 Web 应用）。

## 启动

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # 填入 ANTHROPIC_API_KEY
uvicorn app.main:app --reload
```

访问 http://127.0.0.1:8000/docs 查看 OpenAPI 文档。

## 测试

```bash
pytest
```

## API 一览

| 资源 | 端点 |
|---|---|
| 项目 | `POST/GET/PATCH/DELETE /api/projects` |
| 世界观 | `PUT/GET /api/projects/{id}/world-overview` |
| Lore | `POST/GET/PATCH/DELETE /api/lore` |
| 人物 | `POST/GET/PATCH/DELETE /api/characters` |
| 章节 | `POST/GET/PATCH/DELETE /api/chapters` |
| 章节生成（SSE） | `POST /api/chapters/{id}/generate` |
| 生成日志 | `GET /api/generation-logs?chapter_id=X` / `GET /api/generation-logs/{id}` |
| LLM | `POST /api/llm/ping` |
