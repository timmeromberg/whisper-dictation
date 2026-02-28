"""Tests for TextCleaner."""

from __future__ import annotations

import pytest

from cleaner import TextCleaner


@pytest.fixture()
def cleaner() -> TextCleaner:
    return TextCleaner(text_commands=True)


@pytest.fixture()
def cleaner_no_cmds() -> TextCleaner:
    return TextCleaner(text_commands=False)


class TestFillerRemoval:
    def test_removes_single_filler(self, cleaner: TextCleaner) -> None:
        assert cleaner.clean("I uh think so") == "I think so"

    def test_removes_multi_word_filler(self, cleaner: TextCleaner) -> None:
        assert cleaner.clean("You know what I mean it works") == "It works"

    def test_removes_multiple_fillers(self, cleaner: TextCleaner) -> None:
        assert cleaner.clean("Um I basically think uh yes") == "I think yes"

    def test_case_insensitive(self, cleaner: TextCleaner) -> None:
        assert cleaner.clean("UM I think") == "I think"


class TestRepeatedWords:
    def test_removes_repeated(self, cleaner: TextCleaner) -> None:
        assert cleaner.clean("I I think so") == "I think so"

    def test_removes_repeated_the(self, cleaner: TextCleaner) -> None:
        assert cleaner.clean("the the cat") == "The cat"


class TestTextCommands:
    def test_period(self, cleaner: TextCleaner) -> None:
        assert cleaner.clean("Hello period") == "Hello."

    def test_comma(self, cleaner: TextCleaner) -> None:
        assert cleaner.clean("Hello comma world") == "Hello, world"

    def test_new_line(self, cleaner: TextCleaner) -> None:
        assert cleaner.clean("Hello new line world") == "Hello\nworld"

    def test_new_paragraph(self, cleaner: TextCleaner) -> None:
        assert cleaner.clean("Hello new paragraph world") == "Hello\n\nworld"

    def test_question_mark(self, cleaner: TextCleaner) -> None:
        assert cleaner.clean("Really question mark") == "Really?"

    def test_disabled(self, cleaner_no_cmds: TextCleaner) -> None:
        # With text commands disabled, "period" stays as-is
        result = cleaner_no_cmds.clean("Hello period")
        assert "period" in result.lower()


class TestEdgeCases:
    def test_empty_string(self, cleaner: TextCleaner) -> None:
        assert cleaner.clean("") == ""

    def test_whitespace_only(self, cleaner: TextCleaner) -> None:
        assert cleaner.clean("   ") == "   "

    def test_no_changes_needed(self, cleaner: TextCleaner) -> None:
        assert cleaner.clean("Hello world") == "Hello world"

    def test_capitalizes_first_letter(self, cleaner: TextCleaner) -> None:
        assert cleaner.clean("uh hello") == "Hello"

    def test_cleans_space_before_punct(self, cleaner: TextCleaner) -> None:
        assert cleaner.clean("Hello , world") == "Hello, world"
