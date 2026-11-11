"""
Tests for the ETL orchestration and S3 upload (cli.py), using moto to simulate AWS.

No test touches the network or a real AWS account: moto intercepts all boto3/S3
calls, AWS credentials are forced to fake values, and the Hacker News client
functions are replaced with in-memory fakes.

Covered:
- save_to_parquet writes a readable Parquet object with the rows it was given
  (reading it back also catches a forgotten buffer.seek(0), which uploads 0 bytes).
- save_to_parquet preserves a missing optional field (url) as null.
- main() skips failed fetches and non-story items, and uploads the rest under a
  timestamped key.
- main() aborts and uploads nothing when there are no IDs or no valid stories.
"""

import io
import re

import boto3
import pyarrow.parquet as pq
import pytest
from moto import mock_aws

from aws_etl_news import cli

REGION = "us-east-1"

STORY = {
    "id": 8863,
    "title": "My YC app: Dropbox - Throw away your USB drive",
    "by": "dhouston",
    "time": 1175714200,
    "url": "http://www.getdropbox.com/u/2/screencast.html",
    "score": 104,
    "descendants": 71,
    "type": "story",
}
COMMENT = {
    "id": 999,
    "by": "someone",
    "time": 1175714200,
    "type": "comment"
}


@pytest.fixture(autouse=True)
def fake_aws_credentials(monkeypatch):
    """Force fake credentials so no test can ever reach a real AWS account.

    autouse=True means this runs for every test, including any that build an S3
    client outside the mocked fixture (e.g. the client main() creates itself).
    """
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.delenv("AWS_PROFILE", raising=False)


@pytest.fixture
def s3(monkeypatch):
    """A moto-backed S3 client with the project's bucket already created.

    The `with mock_aws()` stays open for the whole test (via yield), so any client
    built during the test — including the one main() creates — is intercepted too.
    main()'s client uses region eu-central-1, so the bucket is created without a
    LocationConstraint to stay region-agnostic for the test.
    """
    monkeypatch.setattr(cli, "REGION", REGION, raising=False)
    with mock_aws():
        client = boto3.client("s3", region_name=REGION)
        client.create_bucket(Bucket=cli.BUCKET)
        yield client


def use_fake_hn(monkeypatch, story_ids, items):
    """Replace the Hacker News client so main() runs on fixed, in-memory data.

    `items.get` returns None for any id not in the dict, which is exactly how the
    real fetch_item signals a deleted/missing item.
    """
    monkeypatch.setattr(cli, "fetch_top_story_ids", lambda limit: story_ids)
    monkeypatch.setattr(cli, "fetch_item", items.get)


def read_rows(s3, key):
    """Download an object and return its Parquet rows as a list of dicts."""
    body = s3.get_object(Bucket=cli.BUCKET, Key=key)["Body"].read()
    return pq.read_table(io.BytesIO(body)).to_pylist()


def object_keys(s3):
    """Return every object key currently in the bucket."""
    response = s3.list_objects_v2(Bucket=cli.BUCKET)
    return [obj["Key"] for obj in response.get("Contents", [])]


# --- save_to_parquet: ---------------------------------


def test_upload_is_a_readable_parquet_with_the_same_rows(s3):
    cli.save_to_parquet([STORY], s3, cli.BUCKET, "stories.parquet")

    assert read_rows(s3, "stories.parquet") == [STORY]


def test_missing_url_is_stored_as_null(s3):
    story = {**STORY, "url": None}

    cli.save_to_parquet([story], s3, cli.BUCKET, "stories.parquet")

    assert read_rows(s3, "stories.parquet")[0]["url"] is None


# --- main: -----------------------------------------


def test_main_uploads_only_valid_stories_under_partitioned_key(s3, monkeypatch):
    # id 404 is absent from items -> fetch_item returns None;
    # id 999 is a comment -> parse_story returns None (a skipped non-story).
    use_fake_hn(monkeypatch, [8863, 999, 404], {8863: STORY, 999: COMMENT})

    cli.main()

    keys = object_keys(s3)
    assert len(keys) == 1
    assert re.fullmatch(r"date=\d{4}-\d{2}-\d{2}/topstories_\d{8}T\d{6}Z\.parquet", keys[0])
    assert read_rows(s3, keys[0]) == [STORY]


def test_main_aborts_when_no_story_ids(s3, monkeypatch):
    use_fake_hn(monkeypatch, [], {})

    with pytest.raises(RuntimeError, match="story IDs"):
        cli.main()

    assert object_keys(s3) == []


def test_main_aborts_when_no_valid_stories(s3, monkeypatch):
    use_fake_hn(monkeypatch, [999], {999: COMMENT})

    with pytest.raises(RuntimeError, match="no valid stories"):
        cli.main()

    assert object_keys(s3) == []