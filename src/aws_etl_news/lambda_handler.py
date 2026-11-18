"""AWS Lambda entry point: runs the ETL pipeline on invocation."""

from aws_etl_news.cli import main


def handler(event, context):
    main()
    return {"status": "ok"}
