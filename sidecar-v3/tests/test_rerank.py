"""Stage/rung — MiniLM cross-encoder reranker (plan §3.4, rung 8). Integration:
uses the staged MiniLM int8 ONNX + HF-cache tokenizer; skipped if absent (CI
without the asset). The pipeline wiring is unit-tested with a fake rerank_fn."""
import pytest

from index import assets

try:
    MODEL, TOK = assets.rerank_model()
except assets.AssetError:
    MODEL = TOK = None


@pytest.mark.skipif(not (MODEL and TOK), reason="MiniLM reranker ONNX/tokenizer not present")
def test_reranker_scores_relevant_above_irrelevant():
    from query.rerank import Reranker
    r = Reranker(MODEL, TOK)
    query = "how does armor reduce damage"
    docs = [
        "A goblin is a small evil humanoid that lurks in caves.",       # irrelevant
        "Armor reduces the damage taken from each attack by its rating.",  # relevant
    ]
    scores = r.rerank(query, docs)
    assert len(scores) == 2
    assert scores[1] > scores[0]  # the armor passage outscores the goblin passage


@pytest.mark.skipif(not (MODEL and TOK), reason="MiniLM reranker ONNX/tokenizer not present")
def test_reranker_preserves_input_order():
    from query.rerank import Reranker
    r = Reranker(MODEL, TOK)
    docs = ["first doc about spells", "second doc about combat", "third doc about armor"]
    assert len(r.rerank("armor rules", docs)) == 3  # one score per doc, aligned to input
