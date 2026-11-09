-- Ship calls and trade volumes per port and day. Volumes are PortWatch estimates in
-- metric tons, from the change in each ship's draft (AIS data), not official counts.
-- `_total` columns are the sum of the 5 ship types (tankers included).
select
    portid as port_id,
    portname as port_name,
    country,
    iso3 as country_iso3,
    cast(date as date) as activity_date,
    {%- for t in portwatch_vessel_types() %}
    portcalls_{{ t }} as calls_{{ t }},
    import_{{ t }} as import_tonnes_{{ t }},
    export_{{ t }} as export_tonnes_{{ t }},
    {%- endfor %}
    portcalls as calls_total,
    import as import_tonnes_total,
    export as export_tonnes_total
from {{ source('portwatch', 'daily_ports') }}
