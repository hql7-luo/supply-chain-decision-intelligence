-- Observed availability review priorities; no current-on-hand or supplier claims.
WITH last_date AS (SELECT MAX(date) AS end_date FROM daily_sales), recent AS (
  SELECT series_id, AVG(stockout_hours) / 16.0 AS recent_stockout_hour_rate,
         SUM(CASE WHEN stockout_hours>0 THEN 1 ELSE 0 END) AS recent_stockout_days,
         AVG(sales) AS recent_mean_sales
  FROM daily_sales, last_date WHERE date > DATE(end_date, '-28 day') GROUP BY series_id
)
SELECT d.*, r.*, CASE
       WHEN recent_stockout_hour_rate >= 0.25 THEN 'Critical'
       WHEN recent_stockout_hour_rate >= 0.10 THEN 'High Risk'
       WHEN recent_stockout_days > 0 OR s.sales_cv > 1 OR recent_mean_sales = 0 THEN 'Watch'
       ELSE 'Healthy' END AS availability_status
FROM recent r JOIN dim_series d USING(series_id) JOIN series_summary s USING(series_id)
ORDER BY CASE availability_status WHEN 'Critical' THEN 0 WHEN 'High Risk' THEN 1
         WHEN 'Watch' THEN 2 ELSE 3 END,
         recent_stockout_hour_rate DESC, recent_stockout_days DESC, s.sales_cv DESC, series_id;
