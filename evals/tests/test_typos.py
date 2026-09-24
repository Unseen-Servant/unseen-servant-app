import random

from evals.retrieval.typos import neighbours, typo, typo_query


def test_neighbours_are_adjacent_keys():
    assert set(neighbours("s")) == {"q", "w", "e", "a", "d", "z", "x", "c"}
    assert neighbours("1") == []


def test_typo_always_changes_the_word_by_one_edit():
    rng = random.Random(0)
    for word in ["fireball", "the", "grappling", "osric"] * 50:
        out = typo(word, rng)
        assert out.lower() != word.lower()
        assert abs(len(out) - len(word)) <= 1


def test_typo_query_is_seeded_and_corrupts_one_eligible_word():
    q = "how does grappling work in 5e?"
    a = typo_query(q, random.Random(7))
    assert a == typo_query(q, random.Random(7))
    typed, word = a
    assert word in {"how", "does", "grappling", "work"}   # "in", "5e" are ineligible
    assert typed != q and typed.count(" ") == q.count(" ")
