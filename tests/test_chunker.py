"""切分器测试。"""

from app.chunker import chunk_auto, chunk_custom, chunk_hierarchy, chunk, ChunkError


def test_auto_basic():
    text = "这是第一段内容。\n\n这是第二段内容。"
    chunks = chunk_auto(text, max_len=800, overlap=80)
    assert len(chunks) >= 1
    assert all(c.char_end <= len(text) for c in chunks)
    assert chunks[0].text == text  # short text fits in one chunk


def test_auto_long_text():
    text = "内容。" * 500  # 2000 chars
    chunks = chunk_auto(text, max_len=800, overlap=80)
    assert len(chunks) > 1
    assert all(len(c.text) <= 800 for c in chunks)


def test_custom_valid():
    text = "x" * 500
    chunks = chunk_custom(text, length=200, overlap_pct=10)
    assert len(chunks) >= 2
    assert all(len(c.text) <= 200 for c in chunks)


def test_custom_invalid_length():
    try:
        chunk_custom("x" * 100, length=50, overlap_pct=10)
        assert False, "should raise"
    except ChunkError as e:
        assert e.status == 400


def test_custom_invalid_overlap():
    try:
        chunk_custom("x" * 200, length=200, overlap_pct=60)
        assert False, "should raise"
    except ChunkError:
        pass


def test_hierarchy():
    text = "# 第一章\n内容一\n\n## 第二节\n内容二\n\n# 第二章\n内容三"
    chunks = chunk_hierarchy(text)
    assert len(chunks) >= 2
    assert any("第一章" in c.text for c in chunks)


def test_empty_text():
    assert chunk_auto("") == []
    assert chunk_custom("") == []
    assert chunk_hierarchy("") == []
