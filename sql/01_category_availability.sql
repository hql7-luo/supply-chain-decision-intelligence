-- Which categories have the most out-of-stock exposure?
-- 16 business-hour bins: 06:00 through 21:59, reconciled against hourly flags.
SELECT category_id, COUNT(*) AS observed_days, COUNT(DISTINCT series_id) AS store_product_series,
       ROUND(AVG(CASE WHEN stockout_hours > 0 THEN 1.0 ELSE 0.0 END), 6) AS stockout_day_rate,
       ROUND(SUM(stockout_hours) / (16.0 * COUNT(*)), 6) AS stockout_hour_rate,
       ROUND(AVG(sales), 6) AS mean_normalized_sales
FROM daily_sales GROUP BY category_id ORDER BY stockout_hour_rate DESC;
