{{
    config(
        materialized='table',
        description='Full price history per item with period-over-period change metrics.'
    )
}}

with base as (

    select * from {{ ref('stg_prices') }}

),

with_lag as (

    select
        item_id,
        product_name,
        brand,
        category,
        keyword,
        current_price,
        original_price,
        discount_pct,
        price_tier,
        rating,
        review_count,
        location,
        item_url,
        snapshot_date,
        scraped_at,

        -- Compute lag once; derived columns reference this alias
        lag(current_price) over (
            partition by item_id
            order by scraped_at
        )                                                           as prev_price

    from base

),

with_changes as (

    select
        *,
        -- Absolute change — references prev_price, not the window expr
        current_price - prev_price                                  as price_change_abs,

        -- Percentage change — also references prev_price
        case
            when prev_price > 0
            then round(
                (current_price - prev_price) / prev_price * 100
            , 2)
            else null
        end                                                         as price_change_pct

    from with_lag

)

select
    item_id,
    product_name,
    brand,
    category,
    keyword,
    current_price,
    original_price,
    discount_pct,
    price_tier,
    prev_price,
    price_change_abs,
    price_change_pct,
    case
        when price_change_abs < 0 then 'decreased'
        when price_change_abs > 0 then 'increased'
        when price_change_abs = 0 then 'unchanged'
        else 'first_seen'
    end                     as price_direction,
    rating,
    review_count,
    location,
    item_url,
    snapshot_date,
    scraped_at

from with_changes
