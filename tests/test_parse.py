"""
Tests for parse_story (parse.py).

Each test documents a design decision of the function:

1. test_parse_successful_with_all_fields
   Happy path: a story with all 8 fields is extracted correctly.
   Fields are checked by name (url, by, score), not by key count,
   so the test does not break if the schema grows later.

2. test_parse_successful_missing_url
   "Option A" decision: missing optional fields are preserved as None,
   not filled with default values. Absent data is not fake data.
   "Ask HN" posts have no url; the pipeline must not break because of that.

3. test_parse_returns_none_for_comment
   Type filter: only items with type == "story" are processed.
   A comment (or any other type) is discarded by returning None.

Design note: parse_story(None) is not tested because, by contract,
cli.py filters the Nones returned by fetch_item before calling parse_story.
Input validation lives in the orchestrator, not in this pure function.

Test items use real Hacker News API fields
(reference: item 8863, the Dropbox story).
"""

from aws_etl_news.parse import parse_story


def test_parse_successful_with_all_fields():
    """A valid dict with all 8 fields is processed correctly."""
    item = {
        "id": 8863,
        "title": "My YC app: Dropbox - Throw away your USB drive",
        "by": "dhouston",
        "time": 1175714200,
        "url": "http://www.getdropbox.com/u/2/screencast.html",
        "score": 104,
        "descendants": 71,
        "type": "story"
    }

    result = parse_story(item)

    assert result is not None
    assert result["url"] == "http://www.getdropbox.com/u/2/screencast.html"
    assert result["by"] == "dhouston"
    assert result["score"] == 104


def test_parse_successful_missing_url():
    """The URL field may be missing from the API without breaking the code."""
    item = {
        "id": 8863,
        "title": "My YC app: Dropbox - Throw away your USB drive",
        "by": "dhouston",
        "time": 1175714200,
        # url intentionally omitted
        "score": 104,
        "descendants": 71,
        "type": "story"
    }

    result = parse_story(item)

    assert result is not None
    assert result["url"] is None  # Absence is handled by returning None


def test_parse_returns_none_for_comment():
    """A non-story item (e.g. a comment) is discarded with None."""
    item = {
        "id": 999,
        "by": "someone",
        "time": 1175714200,
        "descendants": 71,
        "text": "a comment",
        "type": "comment"  # This should invalidate processing
    }

    result = parse_story(item)

    assert result is None  # type is comment, not story, so the function returns None
