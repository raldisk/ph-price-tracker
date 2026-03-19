{{
    config(
        materialized='table',
        description='Daily top price movers — items with the largest absolute price changes.'
    )
}}

with history as (

    select * from {{ ref('price_history') }}
    where price_change_abs is not null

),

ranked as (

    select
        snapshot_date,
        item_id,
        product_name,
        brand,
        category,
        keyword,
        prev_price,
        current_price,
        price_change_abs,
        price_change_pct,
        price_direction,
        discount_pct,
        rating,
        review_count,
        item_url,

        -- Rank drops and spikes separately within each day
        rank() over (
            partition by snapshot_date, price_direction
            order by abs(price_change_abs) desc
        )                   as rank_within_direction

    from history
    where price_direction in ('decreased', 'increased')

)

select * from ranked
where rank_within_direction <= 20
order by snapshot_date desc, price_direction, rank_within_direction
