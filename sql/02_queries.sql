-- Representative queries on the warehouse (run after the pipeline has loaded data).
-- psql:  docker compose exec warehouse-db psql -U agri -d agri_dw -f 02_queries.sql

-- 1. Top 10 countries by agricultural emissions in the latest year
SELECT c.country_name, cy.year, ROUND(cy.total_mt::numeric, 1) AS total_mt,
       ROUND(cy.share_of_world_pct::numeric, 2) AS share_of_world_pct, cy.is_estimate
FROM agri.agri_country_year cy
JOIN agri.dim_country c USING (country_code)
WHERE cy.year = (SELECT MAX(year) FROM agri.agri_country_year)
ORDER BY cy.total_mt DESC
LIMIT 10;

-- 2. The Philippines since 2000: total, methane share and emissions per person
SELECT year, ROUND(total_mt::numeric, 2) AS total_mt,
       ROUND((100 * ch4_mt / total_mt)::numeric, 1) AS methane_share_pct,
       ROUND(t_per_person::numeric, 3) AS t_per_person, is_estimate
FROM agri.agri_country_year
WHERE country_code = 'PHL' AND year >= 2000
ORDER BY year;

-- 3. Which gas dominates? Methane vs nitrous oxide share, world, by decade
SELECT (year / 10) * 10 AS decade,
       ROUND((100 * SUM(emissions_mt_co2eq) FILTER (WHERE gas_code = 'CH4') / SUM(emissions_mt_co2eq))::numeric, 1) AS ch4_pct,
       ROUND((100 * SUM(emissions_mt_co2eq) FILTER (WHERE gas_code = 'N2O') / SUM(emissions_mt_co2eq))::numeric, 1) AS n2o_pct,
       ROUND((100 * SUM(emissions_mt_co2eq) FILTER (WHERE gas_code = 'CO2') / SUM(emissions_mt_co2eq))::numeric, 1) AS co2_pct
FROM agri.fact_emissions
GROUP BY decade
ORDER BY decade;

-- 4. ASEAN comparison per person (latest year that has population data)
SELECT c.country_name, cy.year, ROUND(cy.total_mt::numeric, 1) AS total_mt,
       ROUND(cy.t_per_person::numeric, 3) AS t_per_person
FROM agri.agri_country_year cy
JOIN agri.dim_country c USING (country_code)
WHERE cy.country_code IN ('BRN', 'KHM', 'IDN', 'LAO', 'MYS', 'MMR', 'PHL', 'SGP', 'THA', 'VNM')
  AND cy.year = (SELECT MAX(year) FROM agri.agri_country_year WHERE population IS NOT NULL)
ORDER BY cy.t_per_person DESC;

-- 5. Fastest-growing emitters since 2015 (countries above 10 Mt in 2015)
SELECT c.country_name,
       ROUND(a.total_mt::numeric, 1) AS mt_2015,
       ROUND(b.total_mt::numeric, 1) AS mt_latest,
       ROUND((100 * (b.total_mt - a.total_mt) / a.total_mt)::numeric, 1) AS growth_pct
FROM agri.agri_country_year a
JOIN agri.agri_country_year b ON b.country_code = a.country_code
                             AND b.year = (SELECT MAX(year) FROM agri.agri_country_year)
JOIN agri.dim_country c ON c.country_code = a.country_code
WHERE a.year = 2015 AND a.total_mt > 10
ORDER BY growth_pct DESC
LIMIT 10;

-- 6. Data freshness: the latest load of every table
SELECT table_name, MAX(loaded_at) AS last_loaded, COUNT(*) AS number_of_loads
FROM agri.load_audit
GROUP BY table_name
ORDER BY table_name;

-- 7. Check: world agricultural emissions per year (must match EDGAR's GLOBAL TOTAL)
SELECT year, ROUND(SUM(emissions_mt_co2eq)::numeric, 2) AS world_total_mt
FROM agri.fact_emissions
WHERE year >= 2020
GROUP BY year
ORDER BY year;

-- 8. FAOSTAT: what drives agricultural emissions in the Philippines? (latest FAOSTAT year)
SELECT a.activity_group, a.activity_name, f.year,
       ROUND(f.emissions_mt_co2eq::numeric, 2) AS mt_co2eq,
       ROUND((100 * f.emissions_mt_co2eq / SUM(f.emissions_mt_co2eq) OVER ())::numeric, 1) AS share_pct
FROM agri.fact_emissions_by_activity f
JOIN agri.dim_activity a USING (activity_code)
WHERE f.country_code = 'PHL'
  AND f.year = (SELECT MAX(year) FROM agri.fact_emissions_by_activity)
ORDER BY f.emissions_mt_co2eq DESC;

-- 9. FAOSTAT: livestock vs crops, world, every 5 years and the latest year
SELECT f.year, a.activity_group, ROUND(SUM(f.emissions_mt_co2eq)::numeric, 0) AS mt_co2eq
FROM agri.fact_emissions_by_activity f
JOIN agri.dim_activity a USING (activity_code)
WHERE f.year % 5 = 0 OR f.year = (SELECT MAX(year) FROM agri.fact_emissions_by_activity)
GROUP BY f.year, a.activity_group
ORDER BY f.year, a.activity_group;

-- 10. EDGAR vs FAOSTAT: biggest differences in the latest common year (countries above 20 Mt)
SELECT c.country_name, v.year, ROUND(v.edgar_total_mt::numeric, 1) AS edgar_mt,
       ROUND(v.faostat_total_mt::numeric, 1) AS faostat_mt, ROUND(v.difference_pct::numeric, 1) AS difference_pct
FROM agri.edgar_vs_faostat v
JOIN agri.dim_country c USING (country_code)
WHERE v.year = (SELECT MAX(year) FROM agri.edgar_vs_faostat) AND v.edgar_total_mt > 20
ORDER BY ABS(v.difference_pct) DESC
LIMIT 10;
