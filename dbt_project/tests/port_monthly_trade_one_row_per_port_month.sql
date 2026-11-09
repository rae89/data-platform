-- One row per port and month: returns duplicates, which fail the test.
select port_id, month, count(*) as n
from {{ ref('port_monthly_trade') }}
group by all
having count(*) > 1
