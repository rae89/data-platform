-- Monthly ship transits and cargo volumes (metric tons) through each chokepoint, by
-- ship type, with change vs. the same month a year earlier. Shows rerouting, e.g.
-- Red Sea traffic (Bab el-Mandeb, Suez) moving to the Cape of Good Hope, or Panama
-- Canal draft limits. The latest month is partial: filter on is_complete_month.
{%- set measures = [] %}
{%- for m in ['transits', 'tonnes'] %}
{%- for t in portwatch_vessel_types() + ['total'] %}{% do measures.append(m ~ '_' ~ t) %}{% endfor %}
{%- endfor %}

with daily as (
    select * from {{ ref('stg_portwatch__daily_chokepoints') }}
),

monthly as (
    select
        chokepoint_id,
        chokepoint_name,
        cast(date_trunc('month', activity_date) as date) as month,
        count(*) as days_reported,
        {%- for col in measures %}
        sum({{ col }}) as {{ col }}{{ ',' if not loop.last }}
        {%- endfor %}
    from daily
    group by all
),

months as (
    select
        *,
        -- All chokepoints are published together, so one cutoff fits all.
        cast(month + interval 1 month - interval 1 day as date)
            <= (select max(activity_date) from daily) as is_complete_month
    from monthly
)

select
    m.*,
    {%- for col in ['transits_total', 'tonnes_total'] %}
    case when m.is_complete_month then m.{{ col }} / nullif(prior.{{ col }}, 0) - 1 end as {{ col }}_yoy{{ ',' if not loop.last }}
    {%- endfor %}
from months m
left join months prior
    on prior.chokepoint_id = m.chokepoint_id
    and prior.month = cast(m.month - interval 1 year as date)
order by m.chokepoint_name, m.month
