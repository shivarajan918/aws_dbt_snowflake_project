{% set cols= ['BOOKING_ID','NIGHTS_BOOKED','BOOKING_AMOUNT'] %}
SELECT
    {% for col in cols %}
         {{col}}
         {% if not loop.last %},{% endif %}
    {% endfor %}
FROM {{ ref('bronze_bookings') }}
 