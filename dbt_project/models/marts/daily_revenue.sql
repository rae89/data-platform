select
    cast(ordered_at as date) as order_date,
    count(*) as orders,
    sum(amount) as revenue
from {{ ref('stg_orders') }}
where status != 'returned'
group by all
order by order_date
