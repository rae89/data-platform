-- Daily container activity per port (IMF PortWatch estimates), with 7-day averages
-- because single days swing with vessel arrival timing.
select
    activity_date,
    port_id,
    port_name,
    calls_total as port_calls,
    calls_container as container_calls,
    import_tonnes_container as container_import_volume,
    export_tonnes_container as container_export_volume,
    avg(calls_container) over w as container_calls_7d_avg,
    avg(import_tonnes_container) over w as container_import_volume_7d_avg,
    avg(export_tonnes_container) over w as container_export_volume_7d_avg
from {{ ref('stg_portwatch__daily_ports') }}
window w as (partition by port_id order by activity_date rows between 6 preceding and current row)
order by port_name, activity_date
