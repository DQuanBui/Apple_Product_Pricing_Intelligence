{#
    Fails for every row where the column falls outside [min_value, max_value].
    Either bound may be omitted. Written in-house so the project needs no
    external packages (no `dbt deps` step in CI).
#}
{% test accepted_range(model, column_name, min_value=none, max_value=none) %}

select *
from {{ model }}
where {{ column_name }} is not null
  and (
      1 = 0
      {% if min_value is not none %} or {{ column_name }} < {{ min_value }} {% endif %}
      {% if max_value is not none %} or {{ column_name }} > {{ max_value }} {% endif %}
  )

{% endtest %}
