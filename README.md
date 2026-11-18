# aws-etl-news

![CI](https://github.com/Samfez/aws-etl-news/actions/workflows/ci.yml/badge.svg)

ETL pipeline that ingests Hacker News front-page stories and writes them as Parquet files to an S3 bucket on AWS. Runs on a schedule as a containerised AWS Lambda, provisioned end to end with Terraform.

## What it does

1. **Extract** — fetch the current top-story IDs, then each item, from the [Hacker News Firebase API](https://github.com/HackerNews/API).
2. **Transform** — keep only `type == "story"` records and flatten them to eight fields. Missing optional fields (for example `url` on Ask HN posts) stay `null`.
3. **Load** — write the stories as Parquet to an in-memory buffer and upload it to S3 under a key partitioned by ingestion date (`date=YYYY-MM-DD/`).

Each run fetches up to 50 front-page items. A failed ID list or an empty parse result aborts the job; a single item that fails to fetch or parse is skipped with a warning.

In production the pipeline runs unattended: an EventBridge schedule triggers a containerised Lambda, which runs the same code and uploads to S3.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- [Terraform](https://developer.hashicorp.com/terraform) and the [AWS CLI](https://aws.amazon.com/cli/), to provision the infrastructure and run against AWS
- [Docker](https://www.docker.com/), to build the Lambda image
- An AWS CLI profile with permission to deploy the stack and write to the bucket

## Setup

```bash
uv sync --group dev
```

## Provision the infrastructure

The S3 bucket, ECR repository, Lambda, its IAM role and the EventBridge schedule are all defined in `infra/main.tf`. Before applying, set your bucket name and AWS CLI profile there, and use the same bucket name for `BUCKET` in `src/aws_etl_news/cli.py`. S3 bucket names are globally unique, so pick your own.

```bash
aws sso login --profile <your-profile>
cd infra
terraform init
terraform apply
```

## Deploy and schedule

The pipeline runs as a container-image Lambda, triggered by an EventBridge schedule. The Lambda's IAM role is least-privilege: `s3:PutObject` to the bucket only.

```bash
# build for Lambda's architecture, push to ECR, then point the function at it
docker build --platform linux/amd64 --provenance=false -t aws-etl-news .
docker tag aws-etl-news:latest <account>.dkr.ecr.<region>.amazonaws.com/aws-etl-news:latest
docker push <account>.dkr.ecr.<region>.amazonaws.com/aws-etl-news:latest
aws lambda update-function-code --function-name aws-etl-news \
  --image-uri <account>.dkr.ecr.<region>.amazonaws.com/aws-etl-news:latest
```

> Note: pushing a new image to ECR does not update the Lambda. The `update-function-code` step is required for the function to pick it up.

## Run the pipeline

Locally, against AWS:

```bash
AWS_PROFILE=<your-profile> uv run python -m aws_etl_news.cli
```

Or invoke the deployed Lambda directly, without waiting for the schedule:

```bash
aws lambda invoke --function-name aws-etl-news --profile <your-profile> response.json
```

Output lands at:

```text
s3://<your-bucket>/date=<YYYY-MM-DD>/topstories_<UTC timestamp>.parquet
```

For example, `date=2026-11-11/topstories_20261111T093000Z.parquet`. Both the date and the timestamp are UTC and come from the same instant, so a run near midnight always lands in the partition matching its timestamp.

List the uploaded files, across all partitions or for a single day:

```bash
aws s3 ls s3://<your-bucket>/ --recursive --profile <your-profile>
aws s3 ls s3://<your-bucket>/date=<YYYY-MM-DD>/ --profile <your-profile>
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
├── Dockerfile             # Lambda container image
├── pyproject.toml
├── infra/
│   └── main.tf            # S3, ECR, Lambda, IAM role, EventBridge (Terraform)
├── src/aws_etl_news/
│   ├── client.py          # fetch_top_story_ids, fetch_item
│   ├── parse.py           # parse_story (pure function)
│   ├── cli.py             # orchestration and S3 upload
│   └── lambda_handler.py  # Lambda entry point (calls main)
└── tests/
    ├── test_parse.py
    └── test_cli.py        # S3 upload and main(), on moto
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
- **Same logic, three entry points** — `main()` holds the pipeline; it runs as a CLI
  script, under moto in tests, and via the Lambda handler in production, with no code
  changes between them. boto3 picks up the Lambda's IAM role automatically, just as it
  picks up the local profile.
- **Containerised Lambda** — packaged as a container image rather than a zip layer,
  because pyarrow exceeds Lambda's 250 MB unzipped limit. The image is built for
  `linux/amd64` and stored in ECR.
- **Hive-style date partitioning** — keys are prefixed with `date=YYYY-MM-DD/`, so
  query engines such as Athena or Spark can discover the partition column and prune
  by date instead of scanning the whole bucket. The partition is the ingestion date
  (UTC), not the stories' publication `time`.

## Tests

```bash
uv run pytest
```

The tests never touch AWS or the network: S3 is simulated with [moto](https://github.com/getmoto/moto), AWS credentials are fake, and the Hacker News client is replaced with in-memory data.

- `parse_story`: a complete story, a story with no `url`, and a non-story item that is discarded.
- `save_to_parquet`: the uploaded object reads back as Parquet with the same rows, and a missing `url` is stored as `null`.
- `main()`: failed fetches and non-stories are skipped and the rest is uploaded under a `date=YYYY-MM-DD/topstories_<timestamp>.parquet` key; with no IDs or no valid stories it raises and uploads nothing.

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

Done:

- Phase 1: local ingestion to Parquet
- Phase 2: S3 storage on AWS, provisioned with Terraform
- Date-partitioned output (`date=YYYY-MM-DD/`)
- CI: ruff and pytest on every push and PR (GitHub Actions)
- Phase 4: scheduled runs as a containerised Lambda (ECR + EventBridge)

Planned next:

- Transform layer with dbt / SQL over the Parquet in S3
- Production hardening: remote Terraform state (S3), a deploy role, Terraform in CI

## License

MIT. See [LICENSE](LICENSE).
</document_content>