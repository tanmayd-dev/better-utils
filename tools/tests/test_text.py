"""Example tool tests, run by the dashboard's test button via ``python -m pytest``.

They import the tool module the same way user tests would (``import tools.text``
from the project root) — the test runner puts the project root and the tools
directory on ``PYTHONPATH``.
"""

import tools.text


def test_reverse_string():
    assert tools.text.reverse_string("abc") == "cba"
    assert tools.text.reverse_string("") == ""


def test_count_words():
    assert tools.text.count_words("one two two")["words"] == 3
    assert tools.text.count_words("one Two two", unique_only=True)["distinct"] == 2


def test_slugify():
    assert tools.text.slugify("Better Utils!") == "better-utils"
    assert tools.text.slugify("x  y", case="upper") == "X-Y"
