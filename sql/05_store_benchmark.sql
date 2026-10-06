-- Category/product mix differs by store: a descriptive benchmark, not a causal ranking.
SELECT city_id, store_id, COUNT(DISTINCT product_id) AS observed_products,
       ROUND(AVG(CASE WHEN stockout_hours>0 THEN 1.0 ELSE 0.0 END), 6) AS stockout_day_rate,
       ROUND(AVG(stockout_hours)/16.0, 6) AS stockout_hour_rate
FROM daily_sales GROUP BY city_id, store_id ORDER BY stockout_hour_rate DESC;
