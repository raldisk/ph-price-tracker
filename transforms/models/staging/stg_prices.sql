{{
    config(
        materialized='view',
        description='Cleaned, type-cast view over raw price snapshots.'
    )
}}

with source as (

    select * from {{ source('raw', 'price_snapshots') }}

),

cleaned as (

    select
        item_id,
        trim(name)                                          as product_name,
        current_price,
        original_price,
        coalesce(discount_pct, 0.0)                         as discount_pct,
        nullif(trim(brand), '')                             as brand,
        nullif(trim(category), '')                          as category,
        item_url,
        rating,
        coalesce(review_count, 0)                           as review_count,
        nullif(trim(location), '')                          as location,
        lower(trim(keyword))                                as keyword,
        page,
        scraped_at,
        -- Derived temporal fields
        date_trunc('day', scraped_at)                       as snapshot_date,
        extract('hour' from scraped_at)                     as snapshot_hour,
        -- Price tier classification for downstream filtering
        case
            when discount_pct >= 50 then 'deep_discount'
            when discount_pct >= 20 then 'on_sale'
            when discount_pct > 0   then 'minor_discount'
            else 'full_price'
        end                                                  as price_tier

    from source
    where
        current_price > 0
        and item_id is not null
        and name is not null

)

select * from cleaned
