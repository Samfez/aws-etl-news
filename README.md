# aws-etl-news

ETL pipeline that ingests Hacker News front-page stories and writes them as Parquet files to an S3 bucket on AWS.

## What it does

1. **Extract** — fetch the current top-story IDs, then each item, from the [Hacker News Firebase API](https://github.com/HackerNews/API).
2. **Transform** — keep only `type == "story"` records and flatten them to eight fields. Missing optional fields (for example `url` on Ask HN posts) stay `null`.
3. **Load** — write the stories as Parquet to an in-memory buffer and upload it to S3 under a timestamped key.

Each run fetches up to 50 front-page items. A failed ID list or an empty parse result aborts the job; a single item that fails to fetch or parse is skipped with a warning.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- [Terraform](https://developer.hashicorp.com/terraform) and the [AWS CLI](https://aws.amazon.com/cli/), to provision the bucket and run against AWS
- An AWS CLI profile with permission to write to the bucket

## Setup

```bash
uv sync --group dev
```

## Provision the bucket

The bucket is defined in `infra/main.tf`. Before applying, set your bucket name and AWS CLI profile there, and use the same bucket name for `BUCKET` in `src/aws_etl_news/cli.py`. S3 bucket names are globally unique, so pick your own.

```bash
aws sso login --profile <your-profile>
cd infra
terraform init
terraform apply
```

## Run the pipeline

```bash
AWS_PROFILE=<your-profile> uv run python -m aws_etl_news.cli
```

Output lands at:

```text
s3://<your-bucket>/topstories_<UTC timestamp>.parquet
```

List the uploaded files:

```bash
aws s3 ls s3://<your-bucket>/ --profile <your-profile>
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
├── infra/
│   └── main.tf     # S3 bucket (Terraform)
├── src/aws_etl_news/
│   ├── client.py   # fetch_top_story_ids, fetch_item
│   ├── parse.py    # parse_story (pure function)
│   └── cli.py      # orchestration and S3 upload
└── tests/
    ├── test_parse.py
    └── test_cli.py # S3 upload and main(), on moto
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
- **In-memory upload** — the Parquet file is written to a `BytesIO` buffer and sent with
  `put_object`, so nothing touches the local disk.
- **Injected S3 client** — `save_to_parquet` receives the S3 client as a parameter, so
  tests can pass a moto-backed client instead of a real one.

## Tests

```bash
uv run pytest
```

The tests never touch AWS or the network: S3 is simulated with [moto](https://github.com/getmoto/moto), AWS credentials are fake, and the Hacker News client is replaced with in-memory data.

- `parse_story`: a complete story, a story with no `url`, and a non-story item that is discarded.
- `save_to_parquet`: the uploaded object reads back as Parquet with the same rows, and a missing `url` is stored as `null`.
- `main()`: failed fetches and non-stories are skipped and the rest is uploaded; with no IDs or no valid stories it raises and uploads nothing.

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

Phase 1 (local ingestion) and phase 2 (S3 storage on AWS) are done. Planned next:

- Manage IAM with Terraform
- Partition output by ingestion date (`date=YYYY-MM-DD/`)

## License

MIT. See [LICENSE](LICENSE).
