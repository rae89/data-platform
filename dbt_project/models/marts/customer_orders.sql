select
    c.customer_id,
    c.customer_name,
    count(o.order_id) as order_count,
    coalesce(sum(o.amount), 0) as lifetime_value,
    min(o.ordered_at) as first_order_at,
    max(o.ordered_at) as last_order_at
from {{ ref('stg_customers') }} c
left join {{ ref('stg_orders') }} o using (customer_id)
group by all
