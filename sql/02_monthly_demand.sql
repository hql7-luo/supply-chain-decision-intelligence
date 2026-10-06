-- Sales are globally normalized source amounts, not currency revenue or physical units.
SELECT SUBSTR(date, 1, 7) AS month, category_id,
       COUNT(DISTINCT date) AS calendar_days, COUNT(*) AS observations,
       ROUND(SUM(sales), 4) AS normalized_sales,
       ROUND(AVG(sales), 6) AS mean_sales_per_store_product_day
FROM daily_sales GROUP BY month, category_id ORDER BY month, category_id;
