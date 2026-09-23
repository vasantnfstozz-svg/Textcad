"""Review of the Text sketch entity (d3c8c85), 2026-09-23.
Measured in probes/text_review_probe.py."""
import pytest

import sketch as sk


def word(text, **kw):
    return sk._text_faces({"kind": "text", "text": text, "size": 10, **kw})


@pytest.mark.parametrize("text", ["☃", "\U0001F600", "A\U0001F600B", "नम"])
def test_a_letter_the_font_lacks_is_refused_not_cut_as_a_box(text):
    """Each of these came back as the font's stand-in box (5 x 6.25 with a
    hole at size 10) and was cut as that, with the row green."""
    with pytest.raises(ValueError, match="has no letter for"):
        word(text)


@pytest.mark.parametrize("text", ["AB", "été", "Ωμ", "café 2026"])
def test_real_letters_still_build(text):
    assert word(text).faces()


def test_the_stand_in_is_found_in_another_font_too():
    with pytest.raises(ValueError, match="'Times New Roman' has no letter"):
        word("☃", font="Times New Roman")


def test_a_number_is_a_word():
    assert len(word(2026).faces()) == len(word("2026").faces())
    assert word(3.5).area == pytest.approx(word("3.5").area)
    with pytest.raises(ValueError, match="the word to write"):
        word(True)
    with pytest.raises(ValueError, match="is empty"):
        word("  ")
