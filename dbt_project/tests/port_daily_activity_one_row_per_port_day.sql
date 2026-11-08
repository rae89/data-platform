-- One row per port and day: returns duplicates, which fail the test.
select port_id, activity_date, count(*) as n
from {{ ref('port_daily_activity') }}
group by all
having count(*) > 1
