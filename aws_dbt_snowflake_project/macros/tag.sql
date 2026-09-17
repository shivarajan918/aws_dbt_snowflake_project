{% macro tag(col) %}
    CASE
        WHEN {{col}} < 100 THEN 'Low'
        WHEN {{col}} < 200 THEN 'Medium'
        ELSE 'High'
    END
{% endmacro %}