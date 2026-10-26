# cli.py
"""ETL orchestration: fetch, parse and write Hacker News stories to Parquet."""


import logging
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from aws_etl_news.client import fetch_item, fetch_top_story_ids
from aws_etl_news.parse import parse_story

logger = logging.getLogger(__name__)  # module-level logger

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def main():

    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    filename = f"topstories_{ts}.parquet"

    # Step 1: Fetch front-page IDs; if the API fails, abort here
    list_top_story_ids = fetch_top_story_ids(50)
    if not list_top_story_ids:
        logger.error("Could not fetch story IDs. Aborting ETL.")
        raise RuntimeError(
            "Failed to fetch Hacker News top story IDs."
        )

    logger.info("Top story ID list fetched.")

    # Step 2: Fetch individual items; if one fails, log a warning and continue
    raw_data = []
    for item_id in list_top_story_ids:
        item = fetch_item(item_id)
        if item is None:
            logger.warning(
                f"Could not fetch item with id={item_id}. "
                "Skipping this item."
            )
            continue
        raw_data.append(item)

    # Step 3: Parse and keep only valid stories. If a key story is malformed, log it and continue.
    cleaned_data = []
    for item in raw_data:
        story = parse_story(item)
        if story is not None:
            cleaned_data.append(story)
        else:
            logger.warning(
                f"Item with id={item.get('id')} discarded: "
                f"not a story or malformed (type={item.get('type')})."
            )

    if not cleaned_data:
        logger.error("Could not clean any data. ETL aborted.")
        raise RuntimeError("Parsing produced no valid stories.")

    logger.info("Data processed successfully.")

    save_to_parquet(cleaned_data, filename)


# Write cleaned_data to a Parquet file in the 'data' folder (repo root) using pyarrow
def save_to_parquet(data, filename):

    # Story schema (matches parse_story)
    schema = pa.schema([
        ("id", pa.int64()),
        ("title", pa.string()),
        ("by", pa.string()),
        ("time", pa.int64()),
        ("url", pa.string()),
        ("score", pa.int64()),
        ("descendants", pa.int64()),
        ("type", pa.string())
    ])

    table = pa.Table.from_pylist(data, schema=schema)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    file_path = DATA_DIR / filename
    pq.write_table(table, str(file_path))
    logger.info(f"File saved successfully at: {file_path}")


if __name__ == "__main__":
    main()
