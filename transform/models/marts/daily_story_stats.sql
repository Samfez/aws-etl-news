SELECT
    ingestion_date,
    count(*) as total_stories,
    avg(score) as avg_score,
    median(score) as median_score,
    sum(score) as sum_score,
    min(score) as min_score,
    max(score) as max_score,
    avg(descendants) as avg_descendants
FROM {{ ref('int_stories_deduped') }}
GROUP BY ingestion_date
ORDER BY ingestion_date