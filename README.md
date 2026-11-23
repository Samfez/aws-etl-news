# aws-etl-news

![CI](https://github.com/Samfez/aws-etl-news/actions/workflows/ci.yml/badge.svg)

A batch data platform that ingests Hacker News front-page stories and turns them into clean, queryable tables on AWS. It runs unattended on a schedule, is provisioned entirely as code, and is tested end to end.

## Architecture

```
Hacker News API
      │   EventBridge schedule → containerised Lambda (Python)
      ▼
S3   date=YYYY-MM-DD/topstories_*.parquet        raw, partitioned
      │   dbt on DuckDB, reading S3 directly
      ▼
staging → intermediate (dedup) → marts           modelled + tested
```

Ingestion (Python on Lambda) lands partitioned Parquet in S3; a dbt layer models it into deduplicated, aggregated tables. Everything — bucket, container registry, function, IAM role and schedule — is defined in Terraform.

**Stack:** Python · AWS (Lambda, S3, ECR, EventBridge, IAM) · Terraform · Docker · dbt · DuckDB · pyarrow · GitHub Actions

## Design decisions

- **Same logic, three entry points** — one `main()` runs as a CLI script, under moto in tests, and via the Lambda handler in production, with no code changes. boto3 picks up the Lambda's IAM role automatically, just as it picks up a local profile. The S3 client is injected as a parameter, so tests pass a moto-backed client instead of a real one.
- **Containerised Lambda** — packaged as a container image (via ECR), not a zip layer, because pyarrow exceeds Lambda's 250 MB unzipped limit. Built for `linux/amd64`.
- **Least-privilege IAM** — the Lambda's role is scoped to `s3:PutObject` on the one bucket, nothing else.
- **Explicit Parquet schema, nulls preserved** — the eight columns are typed explicitly; optional fields absent from the API stay `null` rather than being backfilled. An absent score is not a score of zero.
- **Hive-style date partitioning** — keys are prefixed `date=YYYY-MM-DD/` (ingestion date, UTC), so engines like Athena or Spark can prune by date instead of scanning the whole bucket.
- **Partial vs. fatal failure** — an empty ID list aborts the run; a single item that fails to fetch or parse is skipped with a warning, so one deleted item never fails the batch.

## Transformation (dbt + DuckDB)

dbt models the raw Parquet into layered, tested tables. DuckDB runs the SQL locally and reads the partitioned Parquet from S3 directly — no server, no data load.

| Model                 | Layer        | What it does                                                     |
| --------------------- | ------------ | ---------------------------------------------------------------- |
| `stg_stories`         | staging      | clean and type the raw snapshots                                 |
| `int_stories_deduped` | intermediate | one row per story — its latest snapshot (`QUALIFY ROW_NUMBER()`) |
| `daily_story_stats`   | mart         | per-day aggregates (count, avg/median score, comments)           |
| `story_score_growth`  | mart         | score delta between consecutive snapshots (`LAG`)                |

Five dbt data tests back the models, including a `unique` check on the dedup's `id` — which verifies the deduplication itself, not just the SQL.

## Testing

- **pytest** tests the _code_ (`parse_story`, the S3 upload, `main()`), with S3
  simulated by moto and the API replaced by in-memory data — no AWS, no network.
  This runs in CI (with ruff) on every push and pull request.
- **dbt data tests** test the _data_ (`not_null`, `unique`), run locally against
  the models. Wiring them into CI is on the roadmap.

## Running it

Provision, deploy and run against AWS. Set your own bucket name (S3 names are global) in `infra/main.tf` and `src/aws_etl_news/cli.py`.

```bash
# provision all infrastructure
aws sso login --profile <your-profile>
cd infra && terraform init && terraform apply

# build the image, push to ECR, point the Lambda at it
docker build --platform linux/amd64 --provenance=false -t aws-etl-news .
docker tag aws-etl-news:latest <account>.dkr.ecr.<region>.amazonaws.com/aws-etl-news:latest
docker push <account>.dkr.ecr.<region>.amazonaws.com/aws-etl-news:latest
aws lambda update-function-code --function-name aws-etl-news \
  --image-uri <account>.dkr.ecr.<region>.amazonaws.com/aws-etl-news:latest

# run the transformation layer
cd transform && dbt run && dbt test
```

> Pushing a new image to ECR does not update the Lambda — `update-function-code` is required for the function to pick it up.

Output lands at `s3://<your-bucket>/date=<YYYY-MM-DD>/topstories_<UTC timestamp>.parquet`.

## Project layout

```text
aws-etl-news/
├── Dockerfile                 # Lambda container image
├── infra/main.tf              # S3, ECR, Lambda, IAM, EventBridge (Terraform)
├── src/aws_etl_news/
│   ├── client.py              # Hacker News API client
│   ├── parse.py               # parse_story (pure function)
│   ├── cli.py                 # orchestration and S3 upload
│   └── lambda_handler.py      # Lambda entry point
├── transform/                 # dbt project (models, tests)
└── tests/                     # pytest (parse, upload, main) on moto
```

## Roadmap

Done: ingestion to Parquet · S3 on AWS via Terraform · date partitioning · CI (ruff + pytest) · scheduled containerised Lambda · dbt transformation layer with tests.

Next: port the dbt models to Athena (same SQL, cloud engine) · production hardening (remote Terraform state, a deploy role, Terraform in CI).

## License

MIT. See [LICENSE](LICENSE).
