"""End-to-end index of a real corpus book with the real ONNX models
(PP-DocLayout-M + bge-m3). Integration — skipped when the model assets or the
gitignored corpus aren't present (e.g. CI). Proves the whole pipeline runs on an
actual PDF, not just fakes."""
import os
from pathlib import Path

import pytest

from index import assets
from index.store import DIM, Store
from ingest.pipeline import index_document, make_layout_fn

_CORPUS = Path(os.environ.get("LL_EVAL_CORPUS") or Path(__file__).resolve().parents[2] / "evals" / "corpus")
_BH = _CORPUS / "black_hack" / "TheBlackHack1.2.pdf"


@pytest.mark.skipif(not (assets.available() and _BH.exists()),
                    reason="model assets or corpus PDF not present")
def test_real_index_black_hack(tmp_path):
    store = Store.open(str(tmp_path / "idx.db"))
    layout_fn = make_layout_fn(assets.load_layout_session())
    embed_fn = assets.load_embedder().embed

    rep = index_document(str(_BH), store, layout_fn, embed_fn, doc_id="black_hack_1e")

    assert rep.skipped is False
    assert rep.units > 20 and rep.chunks > 5 and rep.sections >= 1  # a 20-page rulebook
    assert store.counts("black_hack_1e")["units"] == rep.units

    hits = store.search_fts("usage")  # the Usage Die is the Black Hack's signature
    assert hits
    assert store.get_vector(hits[0]).shape == (DIM,)

    # re-index is a no-op (content-hash unchanged)
    assert index_document(str(_BH), store, layout_fn, embed_fn, doc_id="black_hack_1e").skipped is True
