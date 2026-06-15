# NovelAI

AI 辅助小说写作工具（本地优先 Web 应用）。

## 启动

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # 填入 ANTHROPIC_API_KEY
# 注：app.main 将在 Task 2 创建；在此之前运行 uvicorn 会报 ModuleNotFoundError
# uvicorn app.main:app --reload
```

## 测试

```bash
pytest
```
