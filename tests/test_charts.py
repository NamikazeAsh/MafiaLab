import re
import xml.etree.ElementTree as ET

import pytest

from mafia.charts import bars_with_range, dumbbell, ink_on, kpi_row, stacked_bars

NS = {"s": "http://www.w3.org/2000/svg"}


def parse(svg):
    return ET.fromstring(svg)          # raises if the SVG is not well formed XML


def texts(root):
    return [t.text for t in root.iter("{http://www.w3.org/2000/svg}text")]


ROWS = [
    {"label": "Villager", "n_label": "102 decisions", "sound": 20.6, "weak": 76.5, "illogical": 2.9},
    {"label": "Detective", "n_label": "80 decisions", "sound": 78.8, "weak": 21.2, "illogical": 0.0},
    {"label": "Mafia", "n_label": "115 decisions", "sound": 98.3, "weak": 0.9, "illogical": 0.8},
]


def test_text_color_is_chosen_by_contrast_with_the_fill():
    assert ink_on("#0ca30c") == "#0b0b0b" and ink_on("#fab219") == "#0b0b0b"      # dark text on green and yellow
    assert ink_on("#d03b3b") == "#ffffff"                                         # white text on red


def test_stacked_bars_are_valid_and_carry_every_value_as_text():
    root = parse(stacked_bars("Title", "Subtitle", ROWS))
    desc = root.find("s:desc", NS).text
    assert "Villager (102 decisions): sound 20.6%, weak 76.5%, illogical 2.9%." in desc     # a text twin of the data
    t = texts(root)
    assert "20.6%" in t and "76.5%" in t and "78.8%" in t and "21.2%" in t and "98.3%" in t
    assert t.count("sound") == 1 and "weak" in t and "illogical" in t                       # a legend with words, not color alone


def test_a_segment_too_small_for_its_label_gets_the_label_outside_not_clipped():
    root = parse(stacked_bars("T", "S", ROWS))
    t = texts(root)
    assert "2.9%" in t and "0.8%" in t            # the tiny last segments are labelled
    assert "0.9%" not in t                        # a tiny middle segment is left to the table, never squeezed in
    last_labels = [e for e in root.iter("{http://www.w3.org/2000/svg}text") if e.text in ("2.9%", "0.8%")]
    assert all("text-anchor" not in e.attrib for e in last_labels)                          # outside labels start at the bar end


def test_a_zero_share_draws_no_segment_and_the_bars_never_exceed_24px():
    root = parse(stacked_bars("T", "S", ROWS))
    heights = {float(e.attrib["height"]) for e in root.iter("{http://www.w3.org/2000/svg}rect") if "height" in e.attrib and float(e.attrib["height"]) < 40}
    assert heights <= {14.0, 22.0}                # legend swatches and bars only
    titles = [e.text for e in root.iter("{http://www.w3.org/2000/svg}title")]
    assert not any(x and x.startswith("illogical 0.0") for x in titles)


def test_dumbbell_lists_before_after_and_chance_for_every_row():
    rows = [{"label": "Detective check", "before": 84.6, "after": 29.4, "chance": 21.4}, {"label": "Day vote", "before": 28.6, "after": 31.7, "chance": 26.5}]
    root = parse(dumbbell("Title", "Sub", rows))
    assert "Detective check: 84.6% before, 29.4% after, chance 21.4%." in root.find("s:desc", NS).text
    t = texts(root)
    assert "85% to 29%" in t and "29% to 32%" in t and "before the shuffle" in t and "chance" in t


def test_dumbbell_can_show_a_second_result_after_the_change():
    rows = [{"label": "Mafia kill", "before": 55.6, "after": 33.3, "after2": 57.9, "chance": 24.3}]
    svg = dumbbell("Title", "Sub", rows, second_label="3.1 lite, shuffled")
    root = parse(svg)
    assert "57.9% for 3.1 lite, shuffled" in root.find("s:desc", NS).text
    t = texts(root)
    assert "3.1 lite, shuffled" in t and "3.1 lite, shuffled: 58%" in t
    assert svg.count('fill="var(--accent2)"') == 2                                      # the legend dot and the data dot
    assert "accent2" not in dumbbell("T", "S", [{"label": "x", "before": 50, "after": 20, "chance": 25}]).split("</style>")[1]


def test_bars_with_range_mark_a_zero_visibly_and_highlight_one_row():
    rows = [{"key": "control", "label": "No change", "sub": "16 of 108 votes", "value": 14.8, "lo": 9.3, "hi": 22.7},
            {"key": "note", "label": "Own notes", "sub": "0 of 108 votes", "value": 0.0, "lo": 0.0, "hi": 3.4}]
    svg = bars_with_range("Title", "Sub", rows, highlight="note", note="A note.")
    root = parse(svg)
    assert "Own notes (0 of 108 votes): 0.0%, 95% range 0.0% to 3.4%." in root.find("s:desc", NS).text
    assert "0.0%" in texts(root) and "A note." in texts(root)
    assert len(list(root.iter("{http://www.w3.org/2000/svg}circle"))) == 1               # the zero is a marker, not an invisible bar
    assert svg.count('fill="var(--accent)"') >= 1 and svg.count('fill="var(--muted)"') >= 1


def test_kpi_tiles_show_label_value_and_note():
    root = parse(kpi_row([{"label": "Leaks", "value": "0", "note": "in 992 prompts"}, {"label": "Mistake", "value": "0 of 108", "note": "was 16 of 108"}], "Headline"))
    t = texts(root)
    assert "Leaks" in t and "0" in t and "0 of 108" in t and "was 16 of 108" in t


def test_special_characters_in_labels_are_escaped():
    root = parse(kpi_row([{"label": "A & B <c>", "value": "1", "note": 'say "hi"'}], "T & T"))
    assert "A & B <c>" in texts(root)


def test_all_charts_define_light_and_dark_colors_and_no_dashed_lines():
    for svg in (stacked_bars("T", "S", ROWS), dumbbell("T", "S", [{"label": "x", "before": 50, "after": 20, "chance": 25}]),
                kpi_row([{"label": "a", "value": "1", "note": "n"}], "T")):
        assert "prefers-color-scheme: dark" in svg and "--surface" in svg
        assert "stroke-dasharray" not in svg           # gridlines and axes are solid hairlines
