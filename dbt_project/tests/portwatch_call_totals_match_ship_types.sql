-- PortWatch documents the totals as the sum of the 5 ship types. Calls are exact
-- counts; tonnages are rounded, so they aren't checked. Returns mismatched days.
select port_id, activity_date
from {{ ref('stg_portwatch__daily_ports') }}
where calls_total <> {% for t in portwatch_vessel_types() %}calls_{{ t }}{{ ' + ' if not loop.last }}{% endfor %}
union all
select chokepoint_id, activity_date
from {{ ref('stg_portwatch__daily_chokepoints') }}
where transits_total <> {% for t in portwatch_vessel_types() %}transits_{{ t }}{{ ' + ' if not loop.last }}{% endfor %}
