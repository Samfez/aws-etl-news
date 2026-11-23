WITH source AS (
    SELECT *
    FROM {{ source('hn', 'stories') }}
)

SELECT
    id,
    title,
    "by" AS author,
    '''use alias to avoid using SQL reserved word''' url,
    type,
    score,
    descendants,
    to_timestamp(time) AS published_at,
    "date" AS ingestion_date
FROM source
