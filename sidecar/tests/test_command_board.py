"""Session boards (command/canvas.py, command/board.py, design §5.2): JSON
Canvas in Obsidian's own layout, the card operations, and boards following
renames, moves and new sessions."""

from datetime import date

import pytest

from command import board, canvas, prep, vault
from command.vault import Conflict, Invalid, NotFound

# Laid out as Obsidian writes a canvas (jsoncanvas.org's sample.canvas):
# tab-indented, one node per line, no space after a colon, no final break.
OBSIDIAN = (
    "{\n"
    '\t"nodes":[\n'
    '\t\t{"id":"754a8ef995f366bc","type":"group","x":-300,"y":-460,"width":610,"height":200,"label":"Barovia"},\n'
    '\t\t{"id":"8132d4d894c80022","type":"file","file":"Strahd/NPCs/Ismark.md","x":-280,"y":-200,"width":570,"height":560,"color":"6"},\n'
    '\t\t{"id":"59e896bc8da20699","type":"text","text":"Ask [[Ismark]] about the wolves — tonight","x":360,"y":-400,"width":400,"height":400}\n'
    "\t],\n"
    '\t"edges":[\n'
    '\t\t{"id":"6fa11ab87f90b8af","fromNode":"8132d4d894c80022","fromSide":"right","toNode":"59e896bc8da20699","toSide":"left"}\n'
    "\t]\n"
    "}"
)

SESSION = "Sessions/Session 1.md"


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


@pytest.fixture
def camp(tmp_path):
    c = tmp_path / "Strahd"
    write(c / "NPCs" / "Ismark.md", "Brother.\n")
    write(c / "NPCs" / "Ireena.md", "")
    write(c / "Secrets" / "Ravens watch.md", "---\nspent: 2026-10-04\n---\n")
    write(c / "Beats" / "Ambush.md", "")
    write(c / SESSION, "---\ndate: 2026-10-11\nbeats:\n  - \"[[Ambush]]\"\n---\n")
    return c


def board_text(c, session=SESSION):
    return (c / session).with_suffix(".canvas").read_text()


def card(op_id, path, x=0, y=0, width=260, height=180):
    return {"op": "place", "id": op_id, "path": path, "x": x, "y": y, "width": width, "height": height}


# ---------------------------------------------------------------------------
# The format
# ---------------------------------------------------------------------------

def test_a_canvas_obsidian_wrote_round_trips_byte_for_byte():
    assert canvas.dump(canvas.parse(OBSIDIAN)) == OBSIDIAN
    assert canvas.dump(canvas.parse(OBSIDIAN + "\n"), final_newline=True) == OBSIDIAN + "\n"


def test_empty_lists_and_unknown_keys_keep_their_place():
    text = '{"nodes":[],"edges":[],"x-later":{"zoom":1}}'
    assert canvas.dump(canvas.parse(text)) == '{\n\t"nodes":[],\n\t"edges":[],\n\t"x-later":{"zoom":1}\n}'


def test_only_canvas_objects_parse():
    assert canvas.parse("  \n") == {"nodes": [], "edges": []}
    for bad in ("[]", '{"nodes":{}}', '{"edges":[1]}', "{"):
        with pytest.raises(ValueError):
            canvas.parse(bad)


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def test_a_session_without_a_board_reads_empty(camp):
    assert board.read(camp, SESSION) == {"nodes": [], "edges": [], "notes": {}}


def test_cards_resolve_from_the_root_or_from_the_campaign(camp):
    write(camp / "Sessions" / "Session 1.canvas", canvas.dump({"nodes": [
        {"id": "a", "type": "file", "file": "Strahd/NPCs/Ismark.md"},
        {"id": "b", "type": "file", "file": "NPCs/Ireena.md"},
        {"id": "c", "type": "file", "file": "Strahd/NPCs/Gone.md"},
        {"id": "d", "type": "file", "file": "Elsewhere/NPCs/Ismark.md"},
        {"id": "e", "type": "text", "text": "hi"},
    ], "edges": []}))
    assert board.read(camp, SESSION)["notes"] == {"a": "NPCs/Ismark.md", "b": "NPCs/Ireena.md"}


def test_only_a_session_has_a_board(camp):
    with pytest.raises(Invalid):
        board.read(camp, "NPCs/Ismark.md")
    with pytest.raises(NotFound):
        board.read(camp, "Sessions/Session 9.md")


def test_a_board_command_cannot_read_is_refused_not_overwritten(camp):
    write(camp / "Sessions" / "Session 1.canvas", "{ not json")
    with pytest.raises(Invalid):
        board.read(camp, SESSION)
    with pytest.raises(Invalid):
        board.apply(camp, SESSION, [card("a1", "NPCs/Ismark.md")])
    assert board_text(camp) == "{ not json"


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------

def test_placing_and_connecting_writes_obsidians_layout(camp):
    view = board.apply(camp, SESSION, [
        card("a1", "NPCs/Ismark.md"),
        card("b2", "NPCs/Ireena.md", x=320.4, y=-40),
        {"op": "connect", "id": "e1", "source": "a1", "target": "b2", "fromSide": "right", "toSide": "left"},
    ])
    assert board_text(camp) == (
        "{\n"
        '\t"nodes":[\n'
        '\t\t{"id":"a1","type":"file","file":"Strahd/NPCs/Ismark.md","x":0,"y":0,"width":260,"height":180},\n'
        '\t\t{"id":"b2","type":"file","file":"Strahd/NPCs/Ireena.md","x":320,"y":-40,"width":260,"height":180}\n'
        "\t],\n"
        '\t"edges":[\n'
        '\t\t{"id":"e1","fromNode":"a1","fromSide":"right","toNode":"b2","toSide":"left","toEnd":"none"}\n'
        "\t]\n"
        "}"
    )
    assert view["notes"] == {"a1": "NPCs/Ismark.md", "b2": "NPCs/Ireena.md"}


def test_framing_and_removing(camp):
    board.apply(camp, SESSION, [
        card("a1", "NPCs/Ismark.md"),
        card("b2", "NPCs/Ireena.md"),
        {"op": "connect", "id": "e1", "source": "a1", "target": "b2"},
    ])
    view = board.apply(camp, SESSION, [
        {"op": "frame", "id": "a1", "x": 10, "y": 20, "width": 5, "height": 400},
        {"op": "remove", "id": "b2"},
    ])
    assert view["nodes"] == [
        {"id": "a1", "type": "file", "file": "Strahd/NPCs/Ismark.md", "x": 10, "y": 20, "width": board.MIN_SIZE, "height": 400},
    ]
    assert view["edges"] == []


def test_a_line_can_be_removed_on_its_own(camp):
    board.apply(camp, SESSION, [
        card("a1", "NPCs/Ismark.md"),
        card("b2", "NPCs/Ireena.md"),
        {"op": "connect", "id": "e1", "source": "a1", "target": "b2"},
        {"op": "connect", "id": "e2", "source": "b2", "target": "a1"},  # already joined
    ])
    view = board.apply(camp, SESSION, [{"op": "remove", "id": "e1"}])
    assert [n["id"] for n in view["nodes"]] == ["a1", "b2"]
    assert view["edges"] == []


def test_placing_a_note_already_on_the_board_frames_its_card(camp):
    write(camp / "Sessions" / "Session 1.canvas", OBSIDIAN)
    view = board.apply(camp, SESSION, [
        card("fresh", "NPCs/Ismark.md", x=5, y=6),
        {"op": "connect", "id": "e9", "source": "fresh", "target": "754a8ef995f366bc"},
    ])
    ismark = next(n for n in view["nodes"] if n["id"] == "8132d4d894c80022")
    assert (ismark["x"], ismark["y"]) == (5, 6)
    assert len(view["nodes"]) == 3
    assert view["edges"][-1] == {
        "id": "e9", "fromNode": "8132d4d894c80022", "toNode": "754a8ef995f366bc", "toEnd": "none",
    }


def test_an_edit_changes_only_the_line_it_touches(camp):
    write(camp / "Sessions" / "Session 1.canvas", OBSIDIAN)
    board.apply(camp, SESSION, [{"op": "frame", "id": "59e896bc8da20699", "x": 0, "y": 0, "width": 400, "height": 400}])
    before, after = OBSIDIAN.split("\n"), board_text(camp).split("\n")
    assert [i for i, (a, b) in enumerate(zip(before, after, strict=True)) if a != b] == [4]


def test_operations_on_cards_that_are_gone_are_skipped(camp):
    board.apply(camp, SESSION, [card("a1", "NPCs/Ismark.md")])
    view = board.apply(camp, SESSION, [
        {"op": "frame", "id": "zz", "x": 1, "y": 1, "width": 100, "height": 100},
        {"op": "connect", "id": "e1", "source": "a1", "target": "zz"},
        {"op": "remove", "id": "zz"},
    ])
    assert [n["id"] for n in view["nodes"]] == ["a1"]
    assert view["edges"] == []


def test_bad_operations_are_refused_and_nothing_is_written(camp):
    for ops in (
        [{"op": "explode", "id": "a1"}],
        [card("bad id!", "NPCs/Ismark.md")],
        [card("a1", "NPCs/Nobody.md")],
        [{**card("a1", "NPCs/Ismark.md"), "x": "left"}],
    ):
        with pytest.raises((Invalid, NotFound)):
            board.apply(camp, SESSION, ops)
    assert not (camp / "Sessions" / "Session 1.canvas").exists()
    board.apply(camp, SESSION, [card("a1", "NPCs/Ismark.md")])
    with pytest.raises(Conflict):
        board.apply(camp, SESSION, [card("a1", "NPCs/Ireena.md")])


# ---------------------------------------------------------------------------
# The toolbar's cards and lines (docs/roadmap/2026-10-19-command-board-toolbar-design.md)
# ---------------------------------------------------------------------------

def test_text_cards_and_frames_land_in_obsidians_layout(camp):
    board.apply(camp, SESSION, [
        card("a1", "NPCs/Ismark.md"),
        {"op": "add", "id": "t1", "type": "text", "text": "Ask about the wolves", "x": 300, "y": 0,
         "width": 200, "height": 200, "color": "#e6c667"},
        {"op": "add", "id": "g1", "type": "group", "label": "Barovia", "x": -20, "y": -60, "width": 560, "height": 300},
        {"op": "add", "id": "g2", "type": "group", "x": 0, "y": 400, "width": 100, "height": 100},
    ])
    # The frames go before the cards, so Obsidian draws them behind.
    assert board_text(camp) == (
        "{\n"
        '\t"nodes":[\n'
        '\t\t{"id":"g1","type":"group","x":-20,"y":-60,"width":560,"height":300,"label":"Barovia"},\n'
        '\t\t{"id":"g2","type":"group","x":0,"y":400,"width":100,"height":100},\n'
        '\t\t{"id":"a1","type":"file","file":"Strahd/NPCs/Ismark.md","x":0,"y":0,"width":260,"height":180},\n'
        '\t\t{"id":"t1","type":"text","text":"Ask about the wolves","x":300,"y":0,"width":200,"height":200,"color":"#e6c667"}\n'
        "\t],\n"
        '\t"edges":[]\n'
        "}"
    )


def test_a_line_can_carry_a_label_a_colour_and_arrowheads(camp):
    view = board.apply(camp, SESSION, [
        card("a1", "NPCs/Ismark.md"),
        card("b2", "NPCs/Ireena.md"),
        {"op": "connect", "id": "e1", "source": "a1", "target": "b2", "label": "her brother",
         "color": "2", "fromEnd": "arrow", "toEnd": "arrow"},
    ])
    assert view["edges"] == [{
        "id": "e1", "fromNode": "a1", "toNode": "b2", "fromEnd": "arrow", "toEnd": "arrow",
        "color": "2", "label": "her brother",
    }]


def test_set_changes_or_clears_a_field_and_keeps_the_rest(camp):
    write(camp / "Sessions" / "Session 1.canvas", OBSIDIAN)
    board.apply(camp, SESSION, [
        {"op": "set", "id": "754a8ef995f366bc", "label": "Village of Barovia"},
        {"op": "set", "id": "6fa11ab87f90b8af", "label": "asks", "toEnd": "none"},
    ])
    before, after = OBSIDIAN.split("\n"), board_text(camp).split("\n")
    assert [i for i, (a, b) in enumerate(zip(before, after, strict=True)) if a != b] == [2, 7]
    assert '"label":"Village of Barovia"' in after[2]
    assert after[7].endswith('"toSide":"left","label":"asks","toEnd":"none"}')
    view = board.apply(camp, SESSION, [
        {"op": "set", "id": "6fa11ab87f90b8af", "label": None},
        {"op": "set", "id": "59e896bc8da20699", "text": "Tonight", "color": "#8dceee"},
        {"op": "set", "id": "gone", "label": "skipped"},
    ])
    assert "label" not in view["edges"][0]
    text = next(n for n in view["nodes"] if n["id"] == "59e896bc8da20699")
    assert (text["text"], text["color"]) == ("Tonight", "#8dceee")


def test_the_toolbars_bad_operations_are_refused_and_nothing_is_written(camp):
    write(camp / "Sessions" / "Session 1.canvas", OBSIDIAN)
    for ops in (
        [{"op": "add", "id": "x1", "type": "shape", "x": 0, "y": 0, "width": 50, "height": 50}],
        [{"op": "add", "id": "x1", "type": "text", "x": 0, "y": 0, "width": 50, "height": 50}],
        [{"op": "add", "id": "x1", "type": "text", "text": "x" * (board.MAX_TEXT + 1), "x": 0, "y": 0, "width": 50, "height": 50}],
        [{"op": "add", "id": "x1", "type": "text", "text": "", "color": "red", "x": 0, "y": 0, "width": 50, "height": 50}],
        [{"op": "connect", "id": "e2", "source": "8132d4d894c80022", "target": "754a8ef995f366bc", "toEnd": "spear"}],
        [{"op": "set", "id": "8132d4d894c80022", "color": "1"}],
        [{"op": "set", "id": "59e896bc8da20699", "label": "a text card has no label"}],
        [{"op": "set", "id": "59e896bc8da20699", "file": "Strahd/NPCs/Ireena.md"}],
        [{"op": "set", "id": "59e896bc8da20699", "text": None}],
    ):
        with pytest.raises(Invalid):
            board.apply(camp, SESSION, ops)
    with pytest.raises(Conflict):
        board.apply(camp, SESSION, [{"op": "add", "id": "754a8ef995f366bc", "type": "group", "x": 0, "y": 0, "width": 50, "height": 50}])
    assert board_text(camp) == OBSIDIAN


# ---------------------------------------------------------------------------
# Boards follow the vault
# ---------------------------------------------------------------------------

def test_renames_and_moves_rewrite_cards(camp, tmp_path):
    write(camp / "Sessions" / "Session 1.canvas", canvas.dump({"nodes": [
        {"id": "a", "type": "file", "file": "Strahd/NPCs/Ismark.md"},
        {"id": "b", "type": "file", "file": "NPCs/Ireena.md"},
        {"id": "c", "type": "text", "text": "Ask [[Ismark|him]]"},
    ], "edges": []}))
    nodes = lambda: canvas.parse(board_text(camp))["nodes"]  # noqa: E731

    _, rewritten = vault.rename_note(camp, "NPCs/Ismark.md", "Isaac")
    assert "Sessions/Session 1.canvas" in rewritten
    assert [n.get("file") or n.get("text") for n in nodes()] == [
        "Strahd/NPCs/Isaac.md", "NPCs/Ireena.md", "Ask [[Isaac|him]]",
    ]

    vault.move_note(camp, "NPCs/Ireena.md", "Secrets")
    assert nodes()[1]["file"] == "Secrets/Ireena.md"

    vault.rename_track(camp, "NPCs", "Folk")
    assert nodes()[0]["file"] == "Strahd/Folk/Isaac.md"

    vault.rename_campaign(tmp_path, "Strahd", "Barovia")
    moved = tmp_path / "Barovia"
    assert [n.get("file") for n in canvas.parse(board_text(moved))["nodes"][:2]] == [
        "Barovia/Folk/Isaac.md", "Secrets/Ireena.md",
    ]


def test_a_new_session_starts_without_a_board(camp, monkeypatch):
    # Its plan starts empty, so the last board's cards would be notes no
    # beat of it holds.
    monkeypatch.setattr(prep, "today", lambda: date(2026, 10, 18))
    write(camp / "Sessions" / "Session 1.canvas", canvas.dump({"nodes": [
        {"id": "a", "type": "file", "file": "Strahd/NPCs/Ismark.md"},
        {"id": "r", "type": "file", "file": "Strahd/Secrets/Ravens watch.md"},
        {"id": "t", "type": "text", "text": "wolves"},
    ], "edges": [
        {"id": "e1", "fromNode": "a", "toNode": "r"},
        {"id": "e2", "fromNode": "a", "toNode": "t"},
    ]}))
    created = prep.create_session(camp)
    assert not (camp / created["path"]).with_suffix(".canvas").exists()


def test_renaming_a_session_renames_its_board(camp):
    board.apply(camp, SESSION, [card("a1", "NPCs/Ismark.md")])
    new, _ = vault.rename_note(camp, SESSION, "The mists")
    assert board.follow_rename(camp, SESSION, new) == "Sessions/The mists.canvas"
    assert board.read(camp, new)["notes"] == {"a1": "NPCs/Ismark.md"}
    assert board.follow_rename(camp, "NPCs/Ismark.md", "NPCs/Isaac.md") is None


# ---------------------------------------------------------------------------
# Arranging by beat (board toolbar design §6, step 3)
# ---------------------------------------------------------------------------

@pytest.fixture
def planned(camp):
    """Two planned beats sharing Ireena; the first is planned twice."""
    write(camp / "Beats" / "Ambush.md", '---\nnotes:\n  - "[[Ismark]]"\n  - "[[Ireena]]"\n---\n')
    write(camp / "Beats" / "Village.md", '---\nnotes:\n  - "[[Ireena]]"\n  - "[[Ravens watch]]"\n---\n')
    write(camp / SESSION, '---\ndate: 2026-10-11\nbeats:\n  - "[[Ambush]]"\n  - "[[Village]]"\n  - "[[Ambush]]"\n---\n')
    return camp


def frames_by_label(view):
    return {n["label"]: n for n in view["nodes"] if n["type"] == "group"}


def note_cards(view):
    return {view["notes"][n["id"]]: n for n in view["nodes"] if n["id"] in view["notes"]}


def test_arranging_puts_shared_notes_first_then_each_beat_in_plan_order(planned):
    assert board.plan_groups(planned, SESSION) == [
        ("Throughout", ["NPCs/Ireena.md"]),
        ("Ambush", ["NPCs/Ismark.md"]),
        ("Village", ["Secrets/Ravens watch.md"]),
    ]


def test_arranging_frames_each_group_with_its_notes_in_a_row(planned):
    ops = board.arrange(planned, SESSION)
    assert not (planned / SESSION).with_suffix(".canvas").exists()
    view = board.apply(planned, SESSION, ops)
    frames = frames_by_label(view)
    assert list(frames) == ["Throughout", "Ambush", "Village"]
    xs = [f["x"] for f in frames.values()]
    assert xs == sorted(xs) and len({f["y"] for f in frames.values()}) == 1
    cards = note_cards(view)
    assert board._within(cards["NPCs/Ireena.md"], frames["Throughout"])
    assert board._within(cards["NPCs/Ismark.md"], frames["Ambush"])
    assert board._within(cards["Secrets/Ravens watch.md"], frames["Village"])


def test_arranging_again_reuses_the_frames_and_keeps_what_the_gm_put_in_them(planned):
    view = board.apply(planned, SESSION, board.arrange(planned, SESSION))
    ambush = frames_by_label(view)["Ambush"]
    view = board.apply(planned, SESSION, [
        {"op": "add", "id": "s1", "type": "text", "text": "wolves", "color": "3",
         "x": ambush["x"] + 30, "y": ambush["y"] + 60, "width": 100, "height": 100},
        {"op": "frame", "id": ambush["id"], "x": 5000, "y": 5000, "width": ambush["width"] + 300, "height": ambush["height"] + 300},
        {"op": "frame", "id": "s1", "x": 5030, "y": 5060, "width": 100, "height": 100},
    ])
    ops = board.arrange(planned, SESSION)
    assert not [o for o in ops if o["op"] in ("add", "place")]
    view = board.apply(planned, SESSION, ops)
    frames = frames_by_label(view)
    assert len(frames) == 3
    sticky = next(n for n in view["nodes"] if n["id"] == "s1")
    assert board._within(sticky, frames["Ambush"])
    assert board._within(note_cards(view)["NPCs/Ismark.md"], frames["Ambush"])


def test_arranging_leaves_the_rest_of_the_board_and_starts_under_it(planned):
    board.apply(planned, SESSION, [
        {"op": "add", "id": "t1", "type": "text", "text": "Session goals", "x": 400, "y": -500, "width": 260, "height": 100},
        {"op": "add", "id": "g1", "type": "group", "label": "Handouts", "x": 0, "y": -300, "width": 300, "height": 200},
    ])
    ops = board.arrange(planned, SESSION)
    assert not [o for o in ops if o.get("id") in ("t1", "g1")]
    view = board.apply(planned, SESSION, ops)
    frames = frames_by_label(view)
    assert frames["Handouts"]["y"] == -300
    assert min(f["y"] for name, f in frames.items() if name != "Handouts") >= -100 + board.GAP * 2
