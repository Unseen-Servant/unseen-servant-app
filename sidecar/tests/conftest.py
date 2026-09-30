"""
Shared test fixtures for the Legend Lore sidecar.

Key concepts:
- Fixtures are reusable test setup that pytest injects automatically.
  If a test function has a parameter named "client", pytest looks for
  a fixture named "client" and passes its return value.
- Each fixture defaults to "function scope" — recreated for every test.
  This means each test starts with a clean, empty database.
"""

import json
import os

# Skip the cross-encoder model load in unit tests. Tests that need to
# verify rerank-specific behaviour either patch ``rerank_scores`` or
# clear this env var explicitly.
os.environ.setdefault("RERANK_DISABLED", "1")

import pytest
from fastapi.testclient import TestClient

# We can import these safely now — no side effects at import time.
from legend_lore.library_store import LIBRARY_FILENAME, LibraryStore
from legend_lore.service import _embed_text
from server import create_app


# ---------------------------------------------------------------------------
# Library store fixtures
# ---------------------------------------------------------------------------

# all-MiniLM-L6-v2 embeds to 384 dimensions.
TEST_EMBED_MODEL = "test-minilm"
TEST_EMBED_DIM = 384


@pytest.fixture(scope="session")
def test_embed_fn():
    """Real embeddings, no Ollama: fastembed's all-MiniLM-L6-v2.

    The same model ChromaDB's default embedding function used before the
    library store, so the search tests keep their semantics. Loaded once
    per session (~90 MB download on a cold cache).
    """
    from fastembed import TextEmbedding

    model = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")

    def embed(texts):
        return [v.tolist() for v in model.embed(list(texts))]

    return embed


@pytest.fixture
def test_store(tmp_path):
    """Fresh library store in the test's temp dir."""
    store = LibraryStore.open(
        tmp_path / LIBRARY_FILENAME, TEST_EMBED_MODEL, TEST_EMBED_DIM
    )
    yield store
    store.close()


def seed_book(store, embed_fn, path, units, parents=(), game_system="unknown",
              systems=(), page_labels=None):
    """Write one book's EmbedUnits (and parents) straight into the store,
    embedding them the way indexing does. For tests that need exact units
    rather than a PDF run through the chunker."""
    texts = [_embed_text(u) for u in units]
    return store.replace_document(
        str(path), game_system, systems, units, embed_texts=texts,
        vectors=embed_fn(texts) if units else [], parents=list(parents),
        page_labels=page_labels,
    )


# ---------------------------------------------------------------------------
# FastAPI test client
# ---------------------------------------------------------------------------

@pytest.fixture
def client(test_store, test_embed_fn, tmp_path):
    """HTTP test client wired to a temp-dir library store.

    FastAPI's TestClient lets us make HTTP requests without
    starting a real server. It handles the async event loop
    internally, so our test code stays synchronous and simple.

    tmp_path is the data_dir for the store, manifest and settings.
    """
    app = create_app(store=test_store, data_dir=tmp_path, embed_fn=test_embed_fn)
    return TestClient(app)


def sse_events(response):
    """The JSON payloads of an SSE response's ``data:`` frames, in order."""
    return [
        json.loads(line[len("data: "):])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def run_sync(client, body):
    """Sync through ``/api/sync-index-stream``, the route the app uses, and
    return its ``complete`` event's result."""
    response = client.post("/api/sync-index-stream", json=body)
    assert response.status_code == 200, response.text
    result = sse_events(response)[-1]
    assert result.pop("event") == "complete", result
    return result


# ---------------------------------------------------------------------------
# PDF fixture factories
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_pdf_path(tmp_path):
    """Create a small PDF with known TTRPG content.

    The text is deliberately TTRPG-themed so search tests can query
    for "dragon" or "armor class" and get meaningful semantic hits.

    tmp_path is a pytest built-in — a temporary directory that gets
    cleaned up automatically after the test.
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    pdf_path = tmp_path / "dragonbane_monsters.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=letter)

    text_content = (
        "Fire Drake\n"
        "Armor Class: 14\n"
        "Hit Points: 45\n"
        "Movement: 12 (flying 18)\n"
        "A medium-sized dragon that breathes fire in a 30-foot cone. "
        "Fire Drakes are commonly found in volcanic regions and abandoned mines. "
        "They are territorial and will attack intruders on sight. "
        "Weakness: vulnerable to cold damage."
    )

    y = 750
    for line in text_content.split("\n"):
        c.drawString(72, y, line)
        y -= 15

    c.save()
    return pdf_path


@pytest.fixture
def empty_pdf_path(tmp_path):
    """Create a PDF with no extractable text (simulates a scanned PDF).

    Many TTRPG PDFs are scanned images of old books. PyMuPDF can't
    extract text from images without OCR, so the sidecar should
    handle this gracefully rather than crashing.
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    pdf_path = tmp_path / "scanned_module.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=letter)
    c.save()
    return pdf_path


@pytest.fixture
def large_text_pdf_path(tmp_path):
    """Create a PDF with enough text and structure to produce multiple chunks.

    The structure-aware chunker splits at paragraph (`\\n\\n`) boundaries
    within a heading section, so the fixture writes several distinct
    paragraphs with vertical gaps that pymupdf4llm reads as paragraph breaks.
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    pdf_path = tmp_path / "core_rules.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=letter)

    paragraphs = [
        "The adventurer enters the dungeon. " * 20,
        "Combat begins when initiative is rolled and acted upon. " * 20,
        "Spellcasters must concentrate to maintain magical effects. " * 20,
        "Treasure rolls determine loot the party generously gathers. " * 20,
    ]

    y = 750
    for paragraph in paragraphs:
        for i in range(0, len(paragraph), 80):
            line = paragraph[i:i + 80]
            c.drawString(72, y, line)
            y -= 12
            if y < 72:
                c.showPage()
                y = 750
        # Vertical gap between paragraphs so pymupdf4llm emits a blank line.
        y -= 24
        if y < 72:
            c.showPage()
            y = 750

    c.save()
    return pdf_path


@pytest.fixture
def special_chars_pdf_path(tmp_path):
    """PDF with special characters in the filename.

    TTRPG publishers love names like:
    "D&D 5E - Player's Handbook (2024).pdf"

    These can break URL encoding, filesystem operations,
    and ChromaDB chunk IDs.
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    pdf_path = tmp_path / "D&D 5E - Player's Guide (2024).pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=letter)
    c.drawString(72, 750, "This is the player's guide to dragons and dungeons.")
    c.save()
    return pdf_path


# ---------------------------------------------------------------------------
# Game system detection fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def dnd5e_pdf_path(tmp_path):
    """PDF in a D&D 5E folder for game system detection testing."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    dnd_dir = tmp_path / "D&D 5E"
    dnd_dir.mkdir()
    pdf_path = dnd_dir / "player_handbook.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=letter)
    c.drawString(72, 750, "Character creation rules for heroes and adventurers.")
    c.save()
    return pdf_path


@pytest.fixture
def dragonbane_pdf_path(tmp_path):
    """PDF in a Dragonbane folder for game system detection testing."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    db_dir = tmp_path / "Dragonbane"
    db_dir.mkdir()
    pdf_path = db_dir / "dragonbane_core.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=letter)
    c.drawString(72, 750, "Welcome to the Misty Vale, a land of adventure.")
    c.save()
    return pdf_path


@pytest.fixture
def untagged_pdf_path(tmp_path):
    """PDF in a generic folder with no game system hints."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    pdf_path = tmp_path / "random_supplement.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=letter)
    c.drawString(72, 750, "A collection of random tables for any game.")
    c.save()
    return pdf_path
