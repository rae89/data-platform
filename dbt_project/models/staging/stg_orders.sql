select
    id as order_id,
    customer_id,
    lower(status) as status,
    amount_cents / 100.0 as amount,
    cast(ordered_at as timestamp) as ordered_at
from {{ source('raw', 'orders') }}
