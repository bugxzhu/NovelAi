from app.llm.chunking import Chunk, chunk_markdown


def test_chunk_single_paragraph():
    chunks = chunk_markdown("一段文字。")
    assert len(chunks) == 1
    assert isinstance(chunks[0], Chunk)
    assert chunks[0].chunk_type == "paragraph"
    assert chunks[0].text == "一段文字。"
    assert chunks[0].char_count == 5


def test_chunk_multiple_paragraphs():
    chunks = chunk_markdown("第一段。\n\n第二段。\n\n第三段。")
    assert len(chunks) == 3
    assert [c.text for c in chunks] == ["第一段。", "第二段。", "第三段。"]


def test_chunk_empty_content():
    assert chunk_markdown("") == []


def test_chunk_whitespace_only():
    assert chunk_markdown("\n\n   \n\n") == []


def test_chunk_long_paragraph_split():
    long_para = "字" * 1500
    chunks = chunk_markdown(long_para)
    assert len(chunks) >= 2
    for c in chunks:
        assert c.char_count <= 800


def test_chunk_dialogue_detection():
    text = '他说："你好。"她答："你好。"'
    chunks = chunk_markdown(text)
    assert chunks[0].chunk_type == "dialogue"


def test_chunk_description_detection():
    text = "他看见远处的山。她闻到花香。听见鸟鸣。"
    chunks = chunk_markdown(text)
    assert chunks[0].chunk_type == "description"


def test_chunk_chinese_punctuation_split():
    text = "字字字字字字字字字字字字字字字字字字字字字字字字字字字字字字。" * 20
    chunks = chunk_markdown(text)
    assert len(chunks) >= 2


def test_chunk_preserves_text():
    text = "abc测试def"
    chunks = chunk_markdown(text)
    assert chunks[0].text == text


def test_chunk_char_count_correct():
    text = "abc"
    chunks = chunk_markdown(text)
    assert chunks[0].char_count == 3
