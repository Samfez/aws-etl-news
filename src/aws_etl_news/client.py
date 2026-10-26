# client.py
"""HTTP client for the Hacker News API: fetch story IDs and items."""


import logging

import requests

logger = logging.getLogger(__name__)  # module-level logger

BASE_URL = "https://hacker-news.firebaseio.com/v0"


def fetch_top_story_ids(limit: int) -> list[int]:
    """
    Call the Hacker News API to fetch the current list of front-page
    (Top Stories) IDs, limited to 'limit' items.

    Args:
        limit (int): Maximum number of story IDs to return.

    Returns:
        list[int]: A list of up to 'limit' front-page IDs (integers).
        list: An empty list if the request fails.
    """
    url = f"{BASE_URL}/topstories.json"

    try:
        response = requests.get(url, timeout=10)

        response.raise_for_status()

        story_ids = response.json()

        if isinstance(story_ids, list):
            return story_ids[:limit]
        logger.error("Error: API did not return the expected list format.")
        return []

    except requests.exceptions.RequestException as e:
        logger.error(f"Error connecting to the Hacker News API: {e}")
        return []


def fetch_item(item_id: int) -> dict | None:
    """
    Call the Hacker News API with item_id to fetch the item's content.

    Args:
        item_id (int): The item id.

    Returns:
        dict: An object with the item_id content.
        None: if the item does not exist (the API returns null), or if the request fails.
    """

    url = f"{BASE_URL}/item/{item_id}.json"

    try:
        response = requests.get(url, timeout=10)

        response.raise_for_status()

        item_content = response.json()

        # API null = the item does not exist. Expected case, not an error.
        if item_content is None:
            return None

        if isinstance(item_content, dict):
            return item_content
        logger.error(f"Unexpected format for item {item_id}: {type(item_content)}")
        return None

    except requests.exceptions.RequestException as e:
        logger.error(f"Error connecting to the Hacker News API: {e}")
        return None
