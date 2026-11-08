-- Daily container activity per port (IMF PortWatch estimates), with 7-day averages
-- because single days swing with vessel arrival timing.
select
    activity_date,
    port_id,
    port_name,
    port_calls,
    container_calls,
    container_import_volume,
    container_export_volume,
    avg(container_calls) over w as container_calls_7d_avg,
    avg(container_import_volume) over w as container_import_volume_7d_avg,
    avg(container_export_volume) over w as container_export_volume_7d_avg
from {{ ref('stg_portwatch__daily_ports') }}
window w as (partition by port_id order by activity_date rows between 6 preceding and current row)
order by port_name, activity_date
