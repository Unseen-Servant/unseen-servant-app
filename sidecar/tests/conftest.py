"""
Shared test fixtures for the Legend Lore sidecar.

Key concepts:
- Fixtures are reusable test setup that pytest injects automatically.
  If a test function has a parameter named "client", pytest looks for
  a fixture named "client" and passes its return value.
- Each fixture defaults to "function scope" — recreated for every test.
  This means each test starts with a clean, empty database.
"""

import pytest
import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
from fastapi.testclient import TestClient

# We can import these safely now — no side effects at import time.
from server import create_app


# ---------------------------------------------------------------------------
# ChromaDB fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def test_chroma_client():
    """Fresh in-RAM ChromaDB client for each test.

    Split out from ``test_collection`` so tests can exercise endpoints
    that recreate the collection (e.g. delete-index).
    """
    return chromadb.EphemeralClient()


@pytest.fixture
def test_embedding_function():
    """ChromaDB's built-in ONNX (MiniLM) embedding function.

    Real embeddings, no Ollama needed. Used for both the test collection
    and any collection recreated by the endpoints under test.
    """
    return DefaultEmbeddingFunction()


@pytest.fixture
def test_collection(test_chroma_client, test_embedding_function):
    """Fresh in-memory ChromaDB collection for each test.

    EphemeralClient instances share state within a process, so delete
    the collection first to ensure each test starts clean.
    """
    try:
        test_chroma_client.delete_collection("ttrpg_docs_test")
    except Exception:
        pass

    return test_chroma_client.get_or_create_collection(
        name="ttrpg_docs_test",
        embedding_function=test_embedding_function,
    )


# ---------------------------------------------------------------------------
# FastAPI test client
# ---------------------------------------------------------------------------

@pytest.fixture
def client(test_collection, test_chroma_client, test_embedding_function, tmp_path):
    """HTTP test client wired to an in-memory ChromaDB.

    FastAPI's TestClient lets us make HTTP requests without
    starting a real server. It handles the async event loop
    internally, so our test code stays synchronous and simple.

    tmp_path is used as data_dir for manifest storage during tests.
    The chroma_client and embedding_function are passed through so
    delete-index exercises the full production drop+recreate path.
    """
    app = create_app(
        collection=test_collection,
        data_dir=tmp_path,
        chroma_client=test_chroma_client,
        embedding_function=test_embedding_function,
    )
    return TestClient(app)


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
