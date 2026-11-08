-- Volumes are PortWatch estimates from ship tracking (AIS) data, not official counts.
select
    portid as port_id,
    portname as port_name,
    country,
    cast(date as date) as activity_date,
    portcalls as port_calls,
    portcalls_container as container_calls,
    portcalls_tanker as tanker_calls,
    portcalls_dry_bulk as dry_bulk_calls,
    import as import_volume,
    export as export_volume,
    import_container as container_import_volume,
    export_container as container_export_volume
from {{ source('portwatch', 'daily_ports') }}
