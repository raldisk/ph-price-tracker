{% macro median(column) %}
  {#
    Cross-database median macro.

    DuckDB supports native median(col) syntax.
    PostgreSQL requires PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY col).

    Usage in SQL models:
      {{ median('current_price') }}
  #}
  {% if target.type == 'duckdb' %}
    median({{ column }})
  {% elif target.type == 'postgres' %}
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY {{ column }})
  {% else %}
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY {{ column }})
  {% endif %}
{% endmacro %}
