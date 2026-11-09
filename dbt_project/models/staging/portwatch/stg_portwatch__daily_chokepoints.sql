-- Ship transits and transit volumes per chokepoint and day (all 28 PortWatch tracks).
-- Volumes are estimates in metric tons of cargo on board. A ship counts once per
-- transit, and again only after 48 hours.
select
    portid as chokepoint_id,
    portname as chokepoint_name,
    cast(date as date) as activity_date,
    {%- for t in portwatch_vessel_types() %}
    n_{{ t }} as transits_{{ t }},
    capacity_{{ t }} as tonnes_{{ t }},
    {%- endfor %}
    n_total as transits_total,
    capacity as tonnes_total
from {{ source('portwatch', 'daily_chokepoints') }}
