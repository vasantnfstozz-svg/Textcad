"""The judge (judge.py) and the checklist it drives in author.author_steps.

The judge is a small local yes/no model. These tests never need it running:
its one HTTP call (`judge._post`) is replaced, so what is locked in is the
contract around it — fail open, the answer shapes, and that a judge's guess
can refuse "done" but can never cost the user a verified design."""
import json
import urllib.error

import pytest

import author
import judge
from document import Document


class Scripted:
    def __init__(self, *replies):
        self.replies = [r if isinstance(r, str) else json.dumps(r)
                        for r in replies]
        self.heard: list[str] = []

    def generate(self, messages):
        self.heard.append(messages[-1]["content"])
        assert self.replies, "the model was asked for more steps than scripted"
        return self.replies.pop(0)


PLAN = ["a round body", "a centre bore"]
DISC = {"name": "washer", "plan": PLAN,
        "add": {"id": "body", "op": "disc",
                "params": {"radius": 20, "thickness": 4}}}
BORE = {"add": {"id": "bore", "op": "with_center_hole",
                "params": {"radius": 10}, "inputs": ["body"]}}
DONE = {"done": True, "spec": {"n_solids": 1}}


@pytest.fixture(autouse=True)
def _judge_on(monkeypatch):
    monkeypatch.setattr(judge, "ENABLED", True)
    monkeypatch.setattr(judge, "_quiet_until", 0.0)


def _answers(**p):
    """A fake server: probability of YES per question name."""
    def post(body):
        assert body["model"] and body["state"] and body["questions"]
        return {"answers": {k: {"type": "noul", "noul": p.get(k, 0.99),
                                "confidence": 0.9} for k in body["questions"]}}
    return post


# ------------------------------------------------------------ the client ---

def test_yes_no_returns_one_probability_per_question(monkeypatch):
    monkeypatch.setattr(judge, "_post", _answers(a=0.93, b=0.04))
    got = judge.yes_no("a washer: body disc, bore", {"a": "round?", "b": "square?"})
    assert got == {"a": 0.93, "b": 0.04}


def test_no_server_means_none_not_an_exception(monkeypatch):
    def down(body):
        raise urllib.error.URLError("connection refused")
    monkeypatch.setattr(judge, "_post", down)
    assert judge.yes_no("x", {"a": "y?"}) is None
    # ...and the judge stays quiet for a while instead of timing out per step
    monkeypatch.setattr(judge, "_post", _answers(a=0.5))
    assert judge.yes_no("x", {"a": "y?"}) is None


def test_malformed_answers_are_dropped_not_trusted(monkeypatch):
    monkeypatch.setattr(judge, "_post", lambda body: {"answers": {
        "a": {"type": "noul", "noul": "high"}, "b": {"type": "noul", "noul": 1.7},
        "c": {"type": "noul", "noul": 0.2}}})
    assert judge.yes_no("x", {"a": "?", "b": "?", "c": "?"}) == {"c": 0.2}
    monkeypatch.setattr(judge, "_post", lambda body: {"unexpected": 1})
    assert judge.yes_no("x", {"a": "?"}) is None


def test_switched_off_never_calls_out(monkeypatch):
    monkeypatch.setattr(judge, "ENABLED", False)
    monkeypatch.setattr(judge, "_post", lambda body: 1 / 0)
    assert judge.yes_no("x", {"a": "?"}) is None


def test_the_hosted_judge_gets_a_bearer_token_and_the_local_one_none(monkeypatch):
    import io
    import urllib.request
    seen = []

    class Resp(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(req, timeout=None):
        seen.append((req.full_url, dict(req.header_items()), timeout))
        return Resp(b'{"answers": {"a": {"type": "noul", "noul": 0.5}}}')
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(judge, "URL", judge.OPENROUTER)
    monkeypatch.setattr(judge, "KEY", "sk-or-test")
    assert judge.yes_no("x", {"a": "?"}) == {"a": 0.5}
    url, headers, timeout = seen[-1]
    assert url == "https://openrouter.ai/api/v1/systemone"
    assert headers.get("Authorization") == "Bearer sk-or-test"
    assert timeout == judge.TIMEOUT_S
    monkeypatch.setattr(judge, "URL", judge.LOCAL)
    monkeypatch.setattr(judge, "KEY", None)
    judge.yes_no("x", {"a": "?"})
    url, headers, _ = seen[-1]
    assert url == "http://127.0.0.1:8080/v1/systemone"
    assert "Authorization" not in headers


# --------------------------------------------------------- the checklist ---

def test_a_missing_plan_element_refuses_done_once_then_passes(monkeypatch):
    calls = []

    def post(body):
        calls.append(body)
        n = body["state"].count("\n- ")            # features in the summary
        return {"answers": {"p0": {"type": "noul", "noul": 0.97},
                            "p1": {"type": "noul", "noul": 0.9 if n >= 2 else 0.03}}}
    monkeypatch.setattr(judge, "_post", post)
    doc = Document(name="untitled")
    m = Scripted(DISC, DONE, BORE, DONE)
    ok, transcript = author.author_steps(doc, "a washer", m)
    assert ok and [f.id for f in doc.features] == ["body", "bore"]
    refusal = m.heard[2]
    assert "REFUSED done (checklist)" in refusal and "a centre bore" in refusal
    assert "a round body" not in refusal
    assert refusal.endswith("Send the step that adds it (JSON only).")
    # the judge read the request and a one-line-per-feature summary
    assert calls[0]["state"].startswith("REQUEST: a washer")
    assert "- body: disc" in calls[0]["state"]
    assert list(calls[0]["questions"]) == ["p0", "p1"]
    assert "a centre bore" in calls[0]["questions"]["p1"]["instructions"]
    assert transcript[-1].startswith("DONE")


def test_no_judge_means_done_is_judged_as_before(monkeypatch):
    def down(body):
        raise urllib.error.URLError("connection refused")
    monkeypatch.setattr(judge, "_post", down)
    doc = Document(name="untitled")
    m = Scripted(DISC, DONE)
    ok, transcript = author.author_steps(doc, "a washer", m)
    assert ok and [f.id for f in doc.features] == ["body"]


def test_a_stubborn_judge_can_neither_loop_nor_lose_the_design(monkeypatch):
    # the judge says "not found" every time: done is refused CHECKLIST_CAP
    # times, those refusals are NOT counted failures, and done then passes
    # with the unconfirmed elements reported instead of the job giving up
    monkeypatch.setattr(judge, "_post", _answers(p0=0.99, p1=0.01))
    doc = Document(name="untitled")
    dones = [DONE] * (author.CHECKLIST_CAP + 1)
    m = Scripted(DISC, *dones)
    events = []
    ok, transcript = author.author_steps(doc, "a washer", m,
                                         on_step=events.append)
    assert ok and [f.id for f in doc.features] == ["body"]
    refused = [e for e in events if e["kind"] == "refused"]
    assert len(refused) == author.CHECKLIST_CAP
    assert transcript[-1].startswith("DONE")
    assert "could not confirm: a centre bore" in transcript[-1]


def test_no_plan_means_no_checklist(monkeypatch):
    monkeypatch.setattr(judge, "_post", lambda body: 1 / 0)   # never asked
    doc = Document(name="untitled")
    plain = {k: v for k, v in DISC.items() if k != "plan"}
    m = Scripted(plain, DONE)
    ok, _ = author.author_steps(doc, "a washer", m)
    assert ok


def test_plan_is_read_on_the_first_reply_only_and_cleaned():
    assert author._plan_items(["  a  body ", "a body", "", 7, "x" * 200]) == \
        ["a body", "x" * 80]
    assert author._plan_items("not a list") == []
    assert len(author._plan_items([str(i) for i in range(30)])) == author.PLAN_MAX


def test_no_checklist_refusal_when_fewer_than_two_steps_remain(monkeypatch):
    # step 1 adds the body, step 2 is the last allowed: refusing done there
    # would only spend the budget, so done passes without a note
    monkeypatch.setattr(judge, "_post", _answers(p0=0.99, p1=0.01))
    doc = Document(name="untitled")
    m = Scripted(DISC, DONE)
    ok, transcript = author.author_steps(doc, "a washer", m, max_steps=2)
    assert ok and not any("checklist" in h for h in m.heard)
    assert "could not confirm" not in transcript[-1]


def test_sketch_sizes_ride_in_the_summary():
    doc = Document(name="s")
    doc.add("s1", "sketch", {"plane": "XY", "offset": 0, "entities": [
        {"kind": "rectangle", "w": 10, "h": 3, "x": 0, "y": 0, "mode": "add"},
        {"kind": "circle", "r": 1.5, "x": 5, "y": 5, "mode": "add"},
        {"kind": "circle", "r": 1.5, "x": 9, "y": 5, "mode": "add"}]})
    line = author._feature_words(doc.get("s1"))
    assert line.startswith("s1: sketch — on XY — ")
    assert "1 rectangle 10×3" in line and "2 circle r1.5" in line


def test_tree_words_fit_the_judge_window():
    doc = Document(name="big")
    for i in range(120):
        doc.add(f"f{i}", "disc", {"radius": 20 + i, "thickness": 4})
    text = author._tree_words("a very long request " * 40, doc)
    assert len(text) <= judge.STATE_CHARS
    assert text.startswith("REQUEST: a very long request")
    assert "- f0: disc" in text
