-- PortWatch reports every measure for these 5 ship types (plus a total).
{% macro portwatch_vessel_types() %}
    {{ return(['container', 'dry_bulk', 'general_cargo', 'roro', 'tanker']) }}
{% endmacro %}
