select
    id as customer_id,
    trim(name) as customer_name,
    lower(email) as email,
    cast(created_at as timestamp) as created_at
from {{ source('raw', 'customers') }}
