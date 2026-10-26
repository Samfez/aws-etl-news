# aws-etl-news

ETL pipeline that ingests Hacker News front-page stories and writes them to Parquet. The extract and parse steps run locally today; the output is shaped for later landing in a cloud data lake.

## What it does

1. **Extract** — fetch the current top-story IDs, then each item, from the [Hacker News Firebase API](https://github.com/HackerNews/API).
2. **Transform** — keep only `type == "story"` records and flatten them to eight fields. Missing optional fields (for example `url` on Ask HN posts) stay `null`.
3. **Load** — write a timestamped Parquet file under `data/` (gitignored).

Each run fetches up to 50 front-page items. A failed ID list or an empty parse result aborts the job; a single item that fails to fetch or parse is skipped with a warning.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

## Setup

```bash
uv sync --group dev
```

## Run the pipeline

```bash
uv run python -m aws_etl_news.cli
```

Output lands at:

```text
data/topstories_<UTC timestamp>.parquet
```

Inspect a file from the terminal:

```bash
uv run python -c "import pyarrow.parquet as pq; t = pq.read_table('data/topstories_YYYYMMDDTHHMMSSZ.parquet'); print(t.schema); print(t.to_pandas())"
```

## Story schema

| Field         | Type   | Notes                                  |
| ------------- | ------ | -------------------------------------- |
| `id`          | int64  | Hacker News item id                    |
| `title`       | string |                                        |
| `by`          | string | Author username                        |
| `time`        | int64  | Unix timestamp                         |
| `url`         | string | Optional; `null` when the API omits it |
| `score`       | int64  |                                        |
| `descendants` | int64  | Comment count                          |
| `type`        | string | Always `"story"` in the written table  |

## Project layout

```text
aws-etl-news/
├── pyproject.toml
├── src/aws_etl_news/
│   ├── client.py   # fetch_top_story_ids, fetch_item
│   ├── parse.py    # parse_story (pure function)
│   └── cli.py      # orchestration and Parquet write
├── tests/
│   └── test_parse.py
└── data/           # gitignored Parquet output
```

## Design decisions

- **Explicit Parquet schema** — the eight columns are typed explicitly rather than
  inferred. Optional integer fields (`score`, `descendants`) can be null, and pyarrow
  preserves nulls in an `int64` column; schema inference would silently widen them to float.
- **Null handling** — optional fields absent from the API are kept as `null`, not
  backfilled with defaults. An absent score is not a score of zero.
- **Partial vs. fatal failure** — an empty ID list or an empty parse result aborts the
  run (nothing to process). A single item failing to fetch or parse is skipped with a
  warning, so one deleted item does not fail the whole batch.
- **pyarrow over pandas** — avoids pandas' float-coercion of nullable integer columns and
  keeps the write dependency-light.

## Tests

```bash
uv run pytest
```

`parse_story` is covered for:

- a complete story (all eight fields)
- a story with no `url`
- a non-story item (`type == "comment"`), which is discarded

## API used

The client calls:

- `GET https://hacker-news.firebaseio.com/v0/topstories.json`
- `GET https://hacker-news.firebaseio.com/v0/item/{id}.json`

Useful probes while developing:

```bash
curl -s 'https://hacker-news.firebaseio.com/v0/topstories.json' | head -c 300; echo
curl -s 'https://hacker-news.firebaseio.com/v0/item/8863.json' | python3 -m json.tool
curl -s 'https://hacker-news.firebaseio.com/v0/maxitem.json'; echo
```

## Roadmap

This is phase 1 (local ingestion). Planned next:

- Write output to S3 (MinIO locally, AWS in production) via a single endpoint switch
- Provision the bucket and IAM with Terraform
- Partition output by ingestion date (`date=YYYY-MM-DD/`)

## License

MIT. See [LICENSE](LICENSE).
