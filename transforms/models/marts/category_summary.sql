{{
    config(
        materialized='table',
        description='Aggregated category price statistics per snapshot date.'
    )
}}

with base as (

    select * from {{ ref('stg_prices') }}
    where category is not null

)

select
    snapshot_date,
    category,
    keyword,
    count(distinct item_id)                                 as unique_items,
    round(avg(current_price), 2)                           as avg_price,
    -- Uses the cross-database {{ median() }} macro (DuckDB: median(), PG: PERCENTILE_CONT)
    round({{ median('current_price') }}, 2)                as median_price,
    min(current_price)                                      as min_price,
    max(current_price)                                      as max_price,
    round(avg(discount_pct), 2)                            as avg_discount_pct,
    count(case when price_tier = 'deep_discount' then 1 end) as deep_discount_count,
    count(case when price_tier = 'on_sale'       then 1 end) as on_sale_count,
    round(avg(rating), 2)                                  as avg_rating,
    sum(review_count)                                       as total_reviews

from base
group by snapshot_date, category, keyword
order by snapshot_date desc, total_reviews desc
