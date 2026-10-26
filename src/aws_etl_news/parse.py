# parse.py
"""Parse raw Hacker News items into flat story records."""


def parse_story(item: dict) -> dict | None:
    """
    Take a raw Hacker News API item and return a dict with only the 8 desired fields,
    or None if the item is not of type 'story'.
    Returned fields (in order): id, title, by, time, url, score, descendants, type.
    Optional fields are extracted with .get() (url may be missing).
    """

    if item.get("type") != "story":
        return None

    return {
        "id": item.get("id"),
        "title": item.get("title"),
        "by": item.get("by"),
        "time": item.get("time"),
        "url": item.get("url"),
        "score": item.get("score"),
        "descendants": item.get("descendants"),
        "type": item.get("type"),
    }
