"""
Unit tests for the chunk_text() function.

Why test this separately?
- It's a pure function: same input always gives same output
- No network, no database, no files — runs in microseconds
- The chunking strategy directly affects search quality
- Edge cases here prevent subtle bugs in indexing

Mental model for overlap:
    With chunk_size=10, overlap=3, step=7:
    Text: "ABCDEFGHIJKLMNOPQRST" (20 chars)
    Chunk 0: "ABCDEFGHIJ" (chars 0–9)
    Chunk 1: "HIJKLMNOPQ" (chars 7–16)
    Chunk 2: "QRST"       (chars 14–17)
    The overlap region "HIJ" appears in both chunk 0 and chunk 1.
"""

from server import chunk_text


def test_short_text_single_chunk():
    """Text shorter than chunk_size produces exactly one chunk."""
    result = chunk_text("Short text")
    assert len(result) == 1
    assert result[0] == "Short text"


def test_exact_chunk_size():
    """Text exactly chunk_size chars produces two chunks.

    Why 2 and not 1? With step=800, the loop hits offset 0 (gets 1000 chars)
    AND offset 800 (gets the last 200 chars). The overlap means the second
    chunk captures the tail — this is by design, ensuring no text is lost
    at boundaries.
    """
    text = "A" * 1000
    result = chunk_text(text, chunk_size=1000, overlap=200)
    assert len(result) == 2
    assert len(result[0]) == 1000
    assert len(result[1]) == 200


def test_overlap_produces_expected_chunks():
    """Verify overlapping chunks share the expected characters."""
    text = "ABCDEFGHIJKLMNOPQRST"
    result = chunk_text(text, chunk_size=10, overlap=3)
    assert result[0] == "ABCDEFGHIJ"
    assert result[1] == "HIJKLMNOPQ"
    # The overlap region "HIJ" appears in both chunks
    assert result[0][-3:] == result[1][:3]


def test_whitespace_only_chunks_filtered():
    """Chunks that are only whitespace should be excluded.

    PDFs often have pages of whitespace (blank pages, form fields).
    Indexing whitespace wastes ChromaDB storage and adds noise.
    """
    text = "Real content" + " " * 2000 + "More content"
    result = chunk_text(text, chunk_size=1000, overlap=200)
    for chunk in result:
        assert chunk.strip(), f"Found whitespace-only chunk: {repr(chunk)}"


def test_empty_string_returns_empty_list():
    """Empty input should return no chunks."""
    result = chunk_text("")
    assert result == []


def test_default_parameters():
    """Verify the defaults match what server.py uses: 1000/200.

    With step=800, text of 1500 chars:
    Chunk 0: chars 0–999   (1000 chars)
    Chunk 1: chars 800–1499 (700 chars)
    """
    text = "A" * 1500
    result = chunk_text(text)  # Should use chunk_size=1000, overlap=200
    assert len(result) == 2
    assert len(result[0]) == 1000
    assert len(result[1]) == 700


def test_chunk_count_for_known_length():
    """Predictable chunk count for a known text length.

    3000 chars with step=800:
    Chunks at offsets: 0, 800, 1600, 2400 → 4 chunks
    """
    text = "X" * 3000
    result = chunk_text(text, chunk_size=1000, overlap=200)
    assert len(result) == 4
