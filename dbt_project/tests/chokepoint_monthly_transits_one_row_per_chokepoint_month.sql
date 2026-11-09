-- One row per chokepoint and month: returns duplicates, which fail the test.
select chokepoint_id, month, count(*) as n
from {{ ref('chokepoint_monthly_transits') }}
group by all
having count(*) > 1
