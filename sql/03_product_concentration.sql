-- Descriptive sales concentration; not monetary ABC because prices/costs are absent.
WITH product_sales AS (
  SELECT product_id, SUM(sales) AS normalized_sales FROM daily_sales GROUP BY product_id
), ranked AS (
  SELECT product_id, normalized_sales,
         SUM(normalized_sales) OVER (ORDER BY normalized_sales DESC, product_id) AS cumulative_sales,
         SUM(normalized_sales) OVER () AS total_sales,
         ROW_NUMBER() OVER (ORDER BY normalized_sales DESC, product_id) AS sales_rank
  FROM product_sales
)
SELECT *, cumulative_sales / NULLIF(total_sales, 0) AS cumulative_share
FROM ranked ORDER BY sales_rank;
