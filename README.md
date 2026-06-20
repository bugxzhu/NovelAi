# NovelAI

AI 辅助小说写作工具（本地优先 Web 应用）。

## 启动

### 后端（端口 8005）

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # 填入 ANTHROPIC_API_KEY
uvicorn app.main:app --reload --port 8005
```

访问 http://127.0.0.1:8005/docs 查看 OpenAPI 文档。

### 前端（端口 3300）

```bash
cd web
npm install
npm run dev
```

访问 http://localhost:3300 使用前端编辑器。

## 测试

```bash
# 后端
pytest

# 前端单元 + 组件
cd web && npm test

# 前端 E2E（需要后端在 8005 运行）
cd web && npm run test:e2e
```

## 数据库迁移（Alembic）

本项目用 Alembic 管理 schema 演进。新增表/列时：

```bash
# 1. 修改 app/memory/schema.py（添加/修改 ORM 类）
# 2. 生成迁移脚本（自动对比 Base.metadata 与当前 DB）
alembic revision --autogenerate -m "描述本次变更"

# 3. 检查 alembic/versions/<新文件>.py，必要时手动调整

# 4. 应用迁移
alembic upgrade head

# 回滚到上一版本
alembic downgrade -1

# 查看当前版本
alembic current
```

**不要再用 `rm data/novelai.db` 重建**——会丢失所有数据。

**开发流程示例（加新表）：**
1. 编辑 `app/memory/schema.py` 加 `class NewTable(Base): ...`
2. `alembic revision --autogenerate -m "add new_table"`
3. 检查生成的迁移文件（特别是 SQLite 不原生支持的 ALTER，autogenerate 会用 batch 模式）
4. `alembic upgrade head`

**测试**：测试用 `tmp_path` + `Base.metadata.create_all()`，不走 Alembic。

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
