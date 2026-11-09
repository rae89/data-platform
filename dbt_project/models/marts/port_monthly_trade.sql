-- Monthly ship calls and trade volumes (metric tons) per port and ship type, with the
-- trade balance, cargo per container call and change vs. the same month a year
-- earlier. PortWatch runs about 9 days behind, so the latest month is partial:
-- filter on is_complete_month for trends. Year-over-year is null for partial months.
{%- set measures = [] %}
{%- for m in ['calls', 'import_tonnes', 'export_tonnes'] %}
{%- for t in portwatch_vessel_types() + ['total'] %}{% do measures.append(m ~ '_' ~ t) %}{% endfor %}
{%- endfor %}

with daily as (
    select * from {{ ref('stg_portwatch__daily_ports') }}
),

monthly as (
    select
        port_id,
        port_name,
        cast(date_trunc('month', activity_date) as date) as month,
        count(*) as days_reported,
        {%- for col in measures %}
        sum({{ col }}) as {{ col }}{{ ',' if not loop.last }}
        {%- endfor %}
    from daily
    group by all
),

latest as (
    select port_id, max(activity_date) as data_through from daily group by all
),

months as (
    select
        monthly.*,
        cast(month + interval 1 month - interval 1 day as date) <= latest.data_through as is_complete_month
    from monthly
    join latest using (port_id)
)

select
    m.*,
    m.export_tonnes_total - m.import_tonnes_total as trade_balance_tonnes,
    (m.import_tonnes_container + m.export_tonnes_container) / nullif(m.calls_container, 0)
        as tonnes_per_container_call,
    {%- for col in ['calls_total', 'import_tonnes_total', 'export_tonnes_total', 'import_tonnes_container'] %}
    case when m.is_complete_month then m.{{ col }} / nullif(prior.{{ col }}, 0) - 1 end as {{ col }}_yoy{{ ',' if not loop.last }}
    {%- endfor %}
from months m
left join months prior
    on prior.port_id = m.port_id
    and prior.month = cast(m.month - interval 1 year as date)
order by m.port_name, m.month
