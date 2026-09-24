"""The MCP door — TextCAD as a tool an OUTSIDE AI calls (REVIEW-QUEUE §13).

`build_design` and `design_part` are the only doors into the design library
that no human clicks, and until the section 13 review they wrote into
`designs/` with a plain `Document.save()`: no owner check, no existence
check, no version tree. The app's own File ▸ Save has refused that since the
section 3 review ("There is already a different design called X"), because a
save landing on somebody else's file destroys it AND grafts this design onto
their version tree — and `build_design(tree)` with no name is called
"untitled", which is a real design with a real history in the user's library.

These tests are the guard: where the MCP writes, what it claims, and what it
says when the tree or the duty it is handed makes no sense. No model is
called and the doorbell is never rung — `_notify_studio` posts to the user's
live server on port 8123.
"""
import json

import pytest

import author
import mcp_server


PLATE_TREE = {"name": "test-plate",
              "features": [{"id": "base_plate", "op": "plate",
                            "params": {"width": 20, "depth": 10,
                                       "thickness": 3}}],
              "spec": {"n_solids": 1}}


RUNG: list[str] = []              # what the doorbell was asked to open


@pytest.fixture()
def out(tmp_path, monkeypatch):
    """Write into a throwaway directory, never the user's library, and never
    ring the doorbell at the live server."""
    monkeypatch.setattr(mcp_server, "OUT", tmp_path)
    monkeypatch.setattr(mcp_server, "_MINE", {}, raising=False)
    RUNG.clear()
    monkeypatch.setattr(mcp_server, "_notify_studio", RUNG.append)
    return tmp_path


def _user_design(out, slug: str) -> dict:
    """A design of the user's, with a version tree, sitting in the library."""
    data = {"name": slug, "features": [
        {"id": "hand_built", "op": "disc",
         "params": {"radius": 9, "thickness": 2}, "inputs": []}], "spec": {}}
    (out / f"{slug}.tcad.json").write_text(json.dumps(data), encoding="utf-8")
    (out / f"{slug}.history").mkdir()
    return data


# ---------------------------------------------------- where it writes -------

def test_build_design_never_writes_over_a_design_it_did_not_write(out):
    mine = _user_design(out, "esp32-remote")
    rep = mcp_server.build_design(dict(PLATE_TREE), export_name="esp32-remote")
    assert rep["verified"], rep
    assert json.loads((out / "esp32-remote.tcad.json").read_text(
        encoding="utf-8")) == mine, "the user's design was overwritten"
    assert rep["recipe_path"] != str(out / "esp32-remote.tcad.json")
    assert rep["design_name"] != "esp32-remote"


def test_a_tree_with_no_name_does_not_land_on_designs_untitled(out):
    mine = _user_design(out, "untitled")
    tree = {"features": list(PLATE_TREE["features"])}
    rep = mcp_server.build_design(tree)
    assert json.loads((out / "untitled.tcad.json").read_text(
        encoding="utf-8")) == mine
    assert rep["design_name"] == "untitled-2"


def test_the_iteration_loop_still_lands_in_one_file(out):
    """regenerate -> POST /api/open/<name> -> look at it in 3D is the whole
    point of the doorbell, so a name THIS server wrote is written again."""
    first = mcp_server.build_design(dict(PLATE_TREE), export_name="my-widget")
    second = mcp_server.build_design(dict(PLATE_TREE), export_name="my-widget")
    assert first["design_name"] == second["design_name"] == "my-widget"
    assert first["recipe_path"] == second["recipe_path"]


def test_a_design_the_user_has_changed_since_i_wrote_it_is_theirs_now(out):
    """ROUND TWO (2026-09-17). `_MINE` was a promise made once and never
    re-checked, and the doorbell's whole purpose is to put the design in front
    of the user in Studio — where the tab is bound to that file, so File ▸ Save
    writes to it (the section 3 owner guard lets the owning tab through). Open
    the AI's part, change the bore, save, ask the AI for one more change: the
    next build_design landed on the same name and the user's edit was gone,
    with nothing said. A name is only still ours while the file is still what
    we wrote."""
    first = mcp_server.build_design(dict(PLATE_TREE), export_name="my-widget")
    recipe = out / "my-widget.tcad.json"
    assert first["recipe_path"] == str(recipe)
    theirs = json.loads(recipe.read_text(encoding="utf-8"))
    theirs["features"][0]["params"]["thickness"] = 9      # the user's own edit
    recipe.write_text(json.dumps(theirs), encoding="utf-8")

    again = mcp_server.build_design(dict(PLATE_TREE), export_name="my-widget")
    assert again["verified"], again
    assert json.loads(recipe.read_text(encoding="utf-8")) == theirs, \
        "the user's edit was overwritten"
    assert again["design_name"] == "my-widget-2"
    assert "changed" in again.get("renamed", "")
    assert RUNG[-1] == "my-widget-2"


def test_the_doorbell_names_the_file_that_was_actually_written(out):
    _user_design(out, "esp32-remote")
    rep = mcp_server.build_design(dict(PLATE_TREE), export_name="esp32-remote")
    assert RUNG == [rep["design_name"]]
    assert out.exists()


def test_design_part_says_the_right_reason_for_the_name_it_landed_on(out,
                                                                    monkeypatch):
    """ROUND THREE. Round two gave `design_part` a "renamed" line of its own,
    with no test and one reason hard-coded: "a design in this library that is
    not mine to overwrite". It has the SAME two reasons `build_design` has, and
    the one it could not say is the one round two's own fix created — the AI
    wrote that file and the USER has changed it since."""
    import studio

    monkeypatch.setattr(studio, "_make_model", lambda: object())

    def _stub(name):
        d = author._to_document(dict(PLATE_TREE, name=name))
        d.rebuild()
        monkeypatch.setattr(author, "author_design", lambda p, m: (d, ["ok"]))

    _stub("test-plate")                        # a free name: ours to iterate in
    first = mcp_server.design_part("a plate")
    assert first["design_name"] == "test-plate" and "renamed" not in first
    again = mcp_server.design_part("a plate")
    assert again["design_name"] == "test-plate" and "renamed" not in again

    recipe = out / "test-plate.tcad.json"      # ...now the USER edits and saves
    edited = json.loads(recipe.read_text(encoding="utf-8"))
    edited["features"][0]["params"]["thickness"] = 9
    recipe.write_text(json.dumps(edited), encoding="utf-8")
    after = mcp_server.design_part("a plate")
    assert after["design_name"] == "test-plate-2"
    assert "changed since I wrote it" in after["renamed"], after["renamed"]
    assert json.loads(recipe.read_text(encoding="utf-8")) == edited

    _stub("esp32-remote")                      # never ours: the other sentence
    _user_design(out, "esp32-remote")
    theirs = mcp_server.design_part("a remote")
    assert theirs["design_name"] == "esp32-remote-2"
    assert "already a design in this library" in theirs["renamed"]


def test_design_names_cannot_escape_the_designs_folder(out):
    rep = mcp_server.build_design(dict(PLATE_TREE),
                                  export_name="../../etc/passwd")
    assert rep["verified"]
    assert ".." not in rep["recipe_path"]
    assert (out / f"{rep['design_name']}.tcad.json").exists()


# ------------------------------------------------- what it is handed --------

def test_a_feature_that_is_not_an_object_is_a_sentence_not_a_crash(out):
    rep = mcp_server.build_design({"features": ["plate"]})
    assert rep["verified"] is False
    assert rep["rejected_before_build"]
    assert not list(out.glob("*.tcad.json"))


def test_list_operations_documents_the_tree_build_design_takes():
    rep = mcp_server.list_operations()
    conv = rep["conventions"]
    assert "ONE STEP PER REPLY" not in conv, \
        "the MCP door takes a WHOLE tree, not one step per reply"
    assert '"features"' in conv and "ALLOWED OPERATIONS" in conv
    assert {c["op"] for c in rep["operations"]} >= {"plate", "sketch", "cut"}


# ------------------------------------------------------ what it claims ------

def test_verify_step_refuses_a_requirement_it_cannot_check(tmp_path):
    rep = mcp_server.verify_step(str(tmp_path / "nothing.step"),
                                 {"size": [40, 30, 5], "wall_thickness": 2})
    assert "matches_spec" not in rep, \
        "a verdict was given on a spec half of which was never checked"
    assert "wall_thickness" in rep["error"]


def test_verify_step_refuses_a_size_that_is_not_three_axes(tmp_path):
    rep = mcp_server.verify_step(str(tmp_path / "nothing.step"),
                                 {"size": [40, 30]})
    assert "matches_spec" not in rep
    assert "size" in rep["error"]


def test_verify_step_still_answers_a_spec_it_can_check(out):
    mcp_server.build_design(dict(PLATE_TREE), export_name="verify-me")
    step = str(out / "verify-me.step")
    rep = mcp_server.verify_step(step, {"size": [20, 10, 3], "n_solids": 1})
    assert rep["matches_spec"], rep["mismatches"]
    assert rep["measured"]["volume"] == pytest.approx(600, rel=1e-3)


# -------------------------------------------- the catalogue the AI reads ----

def test_every_enum_the_catalogue_offers_is_a_value_the_op_accepts():
    """`op_catalog` advertised axis "X"/"Y"/"Z" for polar_pattern while
    `pattern.axis_of` refuses all three by name — a dropdown (dialogs.js
    renders enums as a <select>) whose every option fails."""
    import sketch as sk
    cat = {c["op"]: c for c in author.op_catalog()}
    axis = next(p for p in cat["polar_pattern"]["params"] if p["name"] == "axis")
    assert axis["enum"], "the axis field must still offer the legal values"
    for v in axis["enum"]:
        assert v.strip().lower() in sk.FACE_DIRS, \
            f"polar_pattern refuses axis {v!r}"
