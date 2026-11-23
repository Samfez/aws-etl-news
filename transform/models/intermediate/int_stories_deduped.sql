select *
from {{ref('stg_stories')}}
qualify row_number() over (partition by id order by ingestion_date desc, score desc) = 1