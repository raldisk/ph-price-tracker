{{
    config(
        materialized='table',
        description='Daily top 10 deals — items with ≥30% discount and ≥50 reviews, ranked by discount depth.'
    )
}}

/*
  Grain: one row per (snapshot_date, item_id) — the best qualifying snapshot
         for each item on each day.

  Business rules:
    - discount_pct >= 30  (meaningful discount, not rounding noise)
    - review_count >= 50  (enough social proof to be trustworthy)
    - Top 10 per day by discount_pct descending, ties broken by review_count

  Why price_history as source (not stg_prices)?
  price_history adds price_direction and price_change_pct, which lets us
  flag "new deal" items that dropped into qualifying range today vs items
  that have been on sale for several days.
*/

with qualifying as (

    select
        snapshot_date,
        item_id,
        product_name,
        brand,
        category,
        keyword,
        current_price,
        original_price,
        discount_pct,
        price_tier,
        price_direction,
        price_change_pct,
        rating,
        review_count,
        location,
        item_url,
        scraped_at

    from {{ ref('price_history') }}
    where
        discount_pct    >= 30
        and review_count >= 50
        and current_price > 0

),

deduped as (

    -- Keep only the latest snapshot per item per day
    select distinct on (snapshot_date, item_id)
        *
    from qualifying
    order by snapshot_date, item_id, scraped_at desc

),

ranked as (

    select
        *,
        rank() over (
            partition by snapshot_date
            order by discount_pct desc, review_count desc
        )                               as deal_rank,

        -- Flag items that just entered qualifying range today
        case
            when price_direction = 'decreased'
             and price_change_pct <= -10 then true
            else false
        end                             as is_fresh_drop

    from deduped

)

select
    snapshot_date,
    deal_rank,
    item_id,
    product_name,
    brand,
    category,
    keyword,
    current_price,
    original_price,
    discount_pct,
    price_tier,
    price_change_pct,
    is_fresh_drop,
    rating,
    review_count,
    location,
    item_url,
    scraped_at

from ranked
where deal_rank <= 10
order by snapshot_date desc, deal_rank asc
