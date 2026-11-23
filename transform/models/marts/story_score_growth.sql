with snapshots as (

    select
        id,
        title,
        author,
        ingestion_date,
        score,
        lag(score) over (
            partition by id
            order by ingestion_date, score
        ) as previous_score
    from {{ ref('stg_stories') }}

)

select
    id,
    title,
    author,
    ingestion_date,
    score,
    previous_score,
    score - previous_score as score_delta
from snapshots
where previous_score is not null