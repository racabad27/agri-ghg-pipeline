# CSV vs JSON vs Parquet

**How we compared:** the Airflow task `compare_formats` (`src/utils/file_formats.py`) takes our main table
`agri_country_year` (one row per country and year), writes it as CSV, JSON (one record per line) and
Parquet three times each and keeps the fastest time, then reads each file back and checks whether every
column still has the same type.

## Results from our run

| format   |   size_kb |   write_ms |   read_ms |   rows_read_back | types_preserved   | columns_with_changed_type   |
|:---------|----------:|-----------:|----------:|-----------------:|:------------------|:----------------------------|
| csv      |    1615.2 |      141.4 |      15.9 |            11391 | False             | population                  |
| json     |    3059.4 |       30.6 |      44.6 |            11391 | False             | population                  |
| parquet  |     779   |       29.9 |       9   |            11391 | True              | -                           |


## What we learned

- **Size:** Parquet is the smallest because it stores data by column and compresses it. JSON is the
  largest because every record repeats every column name.
- **Types:** only Parquet brings every column back with the same type. In CSV and JSON the whole-number
  column `population`, which has empty values, comes back as decimals, and all type information has to be
  guessed again when the file is read.
- **Speed:** at about 11,000 rows every format takes milliseconds, so size and correct types matter more
  than speed here. With millions of rows Parquet's advantage grows, especially when only some columns or
  partitions are read.
- **At scale (FAOSTAT):** the FAOSTAT source arrives as a 325 MB CSV with 2.5 million rows (20 MB zipped).
  In staging the same rows are a 12 MB Parquet file, and the curated step reads only the rows it needs
  (Parquet filters) instead of parsing the whole CSV again.
- **When we use each:** Parquet between pipeline layers (types, compression, partitions); CSV for people
  who open the data in Excel; JSON for web apps and APIs.
