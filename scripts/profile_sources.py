"""Profile every raw source BEFORE transforming it (guidelines section 4.3).

Writes Markdown reports to docs/profiling/:
  edgar_profile.md, worldbank_profile.md, faostat_profile.md

Run (inside Docker):  docker compose exec airflow-scheduler python scripts/profile_sources.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so 'import src' works

import json  # noqa: E402
import re  # noqa: E402
import unicodedata  # noqa: E402
import zipfile  # noqa: E402

import pandas as pd  # noqa: E402
import pycountry  # noqa: E402

from src.config import PROJECT_ROOT, RAW_DIR, get_settings  # noqa: E402
from src.extract.edgar import edgar_raw_path  # noqa: E402
from src.extract.faostat import data_csv_name  # noqa: E402
from src.utils.files import read_json  # noqa: E402

OUT_DIR = PROJECT_ROOT / "docs" / "profiling"


def _fold(text: str) -> str:
    """Lower-case text without accents, e.g. 'São Tomé' -> 'sao tome'."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def looks_merged(code: str, name: str) -> bool:
    """True when EDGAR's name joins several countries under one code, e.g. 'Sudan and South Sudan'.
    Real single countries such as 'Trinidad and Tobago' match their official ISO name, so they are skipped."""
    if " and " not in str(name):
        return False
    country = pycountry.countries.get(alpha_3=str(code))
    if country is None:
        return True
    iso_names = {_fold(getattr(country, attr)) for attr in ("name", "official_name", "common_name")
                 if hasattr(country, attr)}
    return _fold(str(name)) not in iso_names


def retrieval_lines(meta: dict) -> list:
    """Access date and method of the copy we profile (guidelines 4.2), with a warning when the
    file was not downloaded by the pipeline itself."""
    when = meta.get("retrieved_at") or meta.get("recorded_at")
    method = meta.get("retrieval_method", "scripted API calls")
    lines = [f"- **Retrieved:** {when} (UTC), {method}"]
    if method not in ("scripted download", "scripted API calls") or meta.get("note"):
        lines.append(f"- **Warning:** this copy was not downloaded by the pipeline ({meta.get('note') or method}). "
                     "Download it with the extract step and run this script again before using these numbers.")
    return lines


def column_table(df: pd.DataFrame, columns: list) -> str:
    """One row per column: type, missing values, unique values, an example."""
    rows = []
    for c in columns:
        s = df[c]
        rows.append({
            "column": str(c), "type": str(s.dtype), "non_null": int(s.notna().sum()),
            "missing": int(s.isna().sum()), "missing_%": round(100 * s.isna().mean(), 2),
            "unique": int(s.nunique()), "example": str(s.dropna().iloc[0]) if s.notna().any() else "",
        })
    return pd.DataFrame(rows).to_markdown(index=False)


def profile_edgar() -> Path:
    s = get_settings()["edgar"]
    path = edgar_raw_path(s["edition"])
    meta = read_json(path.with_name(path.name + ".meta.json"))
    raw = pd.read_excel(path, sheet_name=s["sheet"], engine="openpyxl")  # exactly as in the file
    id_cols = ["Substance", "Sector", "EDGAR Country Code", "Country"]
    year_cols = [c for c in raw.columns if str(c).strip().split(".")[0].isdigit()]
    values = raw[year_cols]

    blank_rows = int(raw[id_cols].isna().all(axis=1).sum())
    data = raw.dropna(subset=id_cols[:3])
    codes = data[["EDGAR Country Code", "Country"]].drop_duplicates()
    non_iso = codes[codes["EDGAR Country Code"].map(lambda c: pycountry.countries.get(alpha_3=str(c)) is None)]
    merged = codes[[looks_merged(c, n) for c, n in codes.itertuples(index=False)]]
    dup_keys = int(data.duplicated(subset=id_cols[:3]).sum())
    missing_by_substance = data.assign(missing=data[year_cols].isna().sum(axis=1)).groupby("Substance")["missing"].sum()
    stats = values.stack().describe()
    not_countries = s["aggregate_codes"] + s["international_codes"]
    agri = data[(data["Sector"] == "Agriculture") & ~data["EDGAR Country Code"].isin(not_countries)]
    agri = agri.melt(id_vars=["Substance"], value_vars=year_cols).dropna()
    agri_stats = (agri.groupby("Substance")["value"].describe()[["count", "mean", "50%", "max"]]
                  .rename(columns={"count": "values", "50%": "median"}))

    lines = [
        f"# Source profile: EDGAR {s['edition']} (sheet `{s['sheet']}`)",
        "",
        f"- File: `{path.name}` ({meta['size_bytes']:,} bytes, SHA-256 `{meta['sha256'][:16]}...`)",
        f"- Link: {meta['url']}",
        *retrieval_lines(meta),
        f"- Shape as read: **{raw.shape[0]:,} rows x {raw.shape[1]} columns** "
        f"(4 ID columns + {len(year_cols)} year columns {year_cols[0]}-{year_cols[-1]})",
        "- Layout: wide (one column per year). Unit: Mt CO2eq per year (GWP-100, IPCC AR5).",
        "",
        "## ID columns",
        column_table(raw, id_cols),
        "",
        "## Year columns (values)",
        f"- Cells: {values.size:,}; missing: {int(values.isna().sum().sum()):,} "
        f"({100 * values.isna().sum().sum() / values.size:.2f}%); zeros: {int((values == 0).sum().sum()):,}; "
        f"negatives: {int((values < 0).sum().sum())}",
        f"- Missing cells per year: min {int(values.isna().sum().min())}, max {int(values.isna().sum().max())}",
        "",
        "Descriptive statistics of all emission values (Mt CO2eq):",
        "",
        stats.to_frame("value").round(4).to_markdown(),
        "",
        "Agriculture, countries only (the part this project uses), per gas (Mt CO2eq):",
        "",
        agri_stats.round(4).to_markdown(),
        "",
        "## Categories",
        "Rows per sector:",
        "",
        data["Sector"].value_counts().to_frame("rows").to_markdown(),
        "",
        "Rows per substance, and missing cells per substance:",
        "",
        pd.concat({"rows": data["Substance"].value_counts(), "missing_cells": missing_by_substance}, axis=1).to_markdown(),
        "",
        "## Data-quality findings",
        f"1. **{blank_rows} completely blank rows** inside the sheet (separators) -> dropped in staging.",
        f"2. **Duplicate keys** (substance, sector, country): {dup_keys}.",
        "3. **Totals mixed with countries**: `GLOBAL TOTAL` and `EU27` rows -> flagged as aggregates, "
        "excluded from country sums.",
        f"4. **{len(non_iso)} codes are not ISO 3166 country codes**: "
        f"{', '.join(f'{r[0]} ({r[1]})' for r in non_iso.itertuples(index=False))}.",
        f"5. **Merged countries** (one code covers several countries): "
        f"{', '.join(f'{r[0]} = {r[1]}' for r in merged.itertuples(index=False))}.",
        "6. **Missing values** are empty cells, not zeros -> kept as 'no estimate' (dropped), never filled with 0.",
        f"7. **Estimates**: years >= {s['fast_track_from_year']} are EDGAR fast-track estimates -> `is_estimate` flag.",
    ]
    out = OUT_DIR / "edgar_profile.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def profile_worldbank() -> Path:
    w = get_settings()["worldbank"]
    pulls = sorted(p for p in (RAW_DIR / "worldbank" / w["indicator"]).glob("pulled=*")
                   if (p / "_manifest.json").exists())
    folder = pulls[-1]  # latest complete pull
    manifest = read_json(folder / "_manifest.json")
    records = []
    for page_file in sorted(folder.glob("page_*.json")):
        with open(page_file, encoding="utf-8") as f:
            records.extend(json.load(f)[1] or [])
    df = pd.DataFrame({
        "countryiso3code": [r.get("countryiso3code") for r in records],
        "country_name": [r["country"]["value"] for r in records],
        "date": [r["date"] for r in records],
        "value": [r["value"] for r in records],
    })
    df["year"] = pd.to_numeric(df["date"])
    codes = df["countryiso3code"].dropna().unique()
    extra = w["extra_country_codes"]
    regions = sorted(c for c in codes if pycountry.countries.get(alpha_3=c) is None and c not in extra)
    per_year = df.groupby("year")["value"].apply(lambda v: int(v.notna().sum()))

    lines = [
        f"# Source profile: World Bank API, indicator `{w['indicator']}` (population)",
        "",
        f"- Pull folder: `{folder.relative_to(PROJECT_ROOT)}` ({manifest['pages']} pages, {manifest['records']:,} records)",
        *retrieval_lines(manifest),
        f"- Source last updated: {manifest.get('source_last_updated')}",
        f"- Shape after flattening: **{df.shape[0]:,} rows x 4 fields** (`countryiso3code`, `country_name`, `date`, "
        "`value`; `year` is derived from `date`)",
        f"- Years: {int(df['year'].min())}-{int(df['year'].max())}; codes: {len(codes)} "
        f"({len(codes) - len(regions)} countries/territories, {len(regions)} regions or income groups)",
        "",
        "## Columns",
        column_table(df, ["countryiso3code", "country_name", "date", "value"]),
        "",
        "## Values",
        df["value"].describe().to_frame("population").round(0).to_markdown(),
        "",
        f"Records with a value in the latest 5 years: "
        f"{', '.join(f'{y}: {n}' for y, n in per_year.tail(5).items())}",
        "",
        "## Data-quality findings",
        f"1. **Regions and income groups are mixed with countries** ({len(regions)} codes, e.g. "
        f"{', '.join(regions[:8])}) -> flagged with `is_country = False`, never joined to countries.",
        f"2. **Missing values**: {int(df['value'].isna().sum())} records have no value -> dropped in staging.",
        f"3. **Duplicates** (code, year): {int(df.duplicated(subset=['countryiso3code', 'date']).sum())}.",
        "4. **Types**: `date` arrives as text -> converted to integer year; `value` to whole numbers.",
        "5. **Different country lists**: EDGAR merges some countries (e.g. Sudan + South Sudan); "
        "config/country_mapping.csv adds their populations up.",
    ]
    out = OUT_DIR / "worldbank_profile.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def read_faostat_long(zip_path: Path) -> tuple[pd.DataFrame, str, tuple]:
    """Read the FAOSTAT CSV from the zip as it is; return it in long form, the layout and the shape as read."""
    member = data_csv_name(zip_path)
    text = {c: "category" for c in ["Area", "Item", "Element", "Source", "Unit", "Flag"]}
    with zipfile.ZipFile(zip_path) as archive, archive.open(member) as f:
        raw = pd.read_csv(f, encoding="utf-8", dtype={"Area Code (M49)": str, **text}, low_memory=False)
    shape = raw.shape
    if {"Year", "Value"} <= set(raw.columns):
        return raw, "normalized (one row per area, item, element, source and year)", shape
    years = [c for c in raw.columns if re.fullmatch(r"Y\d{4}", c)]
    ids = ["Area Code", "Area Code (M49)", "Area", "Item Code", "Item", "Element", "Source", "Unit"]
    long = raw.melt(id_vars=ids, value_vars=years, var_name="Year", value_name="Value")
    long["Flag"] = raw.melt(value_vars=[y + "F" for y in years], value_name="Flag")["Flag"].to_numpy()
    long["Year"] = long["Year"].str[1:].astype(int)
    return long.dropna(subset=["Value"]), "wide (one column per year)", shape


def profile_faostat() -> Path:
    f = get_settings()["faostat"]
    files = sorted(p for p in (RAW_DIR / "faostat").glob("pulled=*/*.zip")
                   if p.with_name(p.name + ".meta.json").exists())
    path = files[-1]  # latest complete download
    meta = read_json(path.with_name(path.name + ".meta.json"))
    df, layout, shape = read_faostat_long(path)

    is_aggregate = (df["Area Code"] >= f["world_area_code"]) | (df["Area Code"] == f["china_area_code"])
    areas = df[["Area Code", "Area Code (M49)", "Area"]].drop_duplicates("Area Code")
    area_is_aggregate = (areas["Area Code"] >= f["world_area_code"]) | (areas["Area Code"] == f["china_area_code"])
    m49 = areas["Area Code (M49)"].astype(str).str.lstrip("'").str.zfill(3)
    no_iso = areas[~area_is_aggregate & m49.map(lambda c: pycountry.countries.get(numeric=c) is None)]
    last_year_by_area = df.groupby("Area Code")["Year"].max()
    no_iso = no_iso.assign(last_year=no_iso["Area Code"].map(last_year_by_area))
    activities = df[(df["Source"] == f["source"]) & (df["Element"] == f["element"])
                    & df["Item Code"].isin(list(f["activities"]))]
    negative = activities[activities["Value"] < 0]
    projections = df[df["Flag"] == f["projection_flag"]]
    duplicates = int(df.duplicated(subset=["Area Code", "Item Code", "Element", "Source", "Year"]).sum())
    wanted = df[(df["Source"] == f["source"]) & (df["Element"] == f["element"])
                & df["Item Code"].isin(list(f["activities"])) & (df["Year"] >= f["first_year"])
                & (df["Flag"] != f["projection_flag"]) & ~is_aggregate]

    lines = [
        "# Source profile: FAOSTAT Emissions Totals (domain GT)",
        "",
        f"- File: `{path.name}` ({meta['size_bytes']:,} bytes, SHA-256 `{meta['sha256'][:16]}...`), "
        f"data file inside: `{data_csv_name(path)}`",
        f"- Link: {meta['url']}",
        *retrieval_lines(meta),
        f"- Layout: {layout}; shape as read: **{shape[0]:,} rows x {shape[1]} columns**; "
        f"values: **{len(df):,}**",
        f"- Years: {int(df['Year'].min())}-{int(df['Year'].max())}; unit: {', '.join(map(str, df['Unit'].unique()))}",
        f"- Areas: {df['Area Code'].nunique()} ({int((~area_is_aggregate).sum())} countries and territories, "
        f"{int(area_is_aggregate.sum())} regions and groups); items: {df['Item Code'].nunique()}; "
        f"elements: {df['Element'].nunique()}; sources: {df['Source'].nunique()}",
        "",
        "## Columns",
        column_table(df, list(df.columns)),
        "",
        "## Categories",
        "Values per source and element:",
        "",
        df.groupby(["Source", "Element"], observed=True).size().reset_index(name="values").to_markdown(index=False),
        "",
        "Flags:",
        "",
        df["Flag"].value_counts().to_frame("values").to_markdown(),
        "",
        "## Values",
        df["Value"].describe().to_frame("value (kt)").round(4).to_markdown(),
        "",
        f"The part this project uses ({f['source']}, {f['element']}, the 8 farm activities, from {f['first_year']}, "
        f"countries only): **{len(wanted):,} values**, years {int(wanted['Year'].min())}-{int(wanted['Year'].max())}. "
        "Per activity (kt CO2eq):",
        "",
        (wanted.groupby("Item", observed=True)["Value"].describe()[["count", "mean", "50%", "max"]]
         .rename(columns={"count": "values", "50%": "median"}).round(2).to_markdown()),
        "",
        "## Data-quality findings",
        f"1. **Totals mixed with countries**: {int((areas['Area Code'] >= f['world_area_code']).sum())} regions and "
        f"groups (codes >= {f['world_area_code']}, e.g. World, Asia, European Union) and 'China' "
        f"(code {f['china_area_code']}, the sum of mainland China, Hong Kong, Macao and Taiwan) -> flagged "
        "`is_aggregate`, never added to country sums.",
        f"2. **Two sources**: {', '.join(f'{k} ({v:,} values)' for k, v in df['Source'].value_counts().items())} -> "
        f"we use `{f['source']}`, FAO's own estimate that exists for every country.",
        f"3. **Several elements** (single gases and CO2-equivalents) -> we use `{f['element']}` "
        "(GWP-100 from IPCC AR5, the same as EDGAR).",
        f"4. **Projections mixed with data**: {len(projections):,} values for "
        f"{', '.join(map(str, sorted(projections['Year'].unique())))} with flag `{f['projection_flag']}` "
        "-> flagged `is_projection`, never used as data.",
        f"5. **Areas without an ISO country code** ({len(no_iso)}): "
        f"{', '.join(f'{r.Area} (last year {r.last_year})' for r in no_iso.itertuples())}. "
        f"Only {' and '.join(no_iso.loc[no_iso['Area Code'].isin(wanted['Area Code']), 'Area'].astype(str))} "
        "have values in the part we use -> mapped to EDGAR codes in config/faostat_area_mapping.csv.",
        f"6. **Negative emissions** where they are impossible ({len(negative)} values in the 8 activities): "
        f"{', '.join(sorted(set(negative['Area'].astype(str) + ' / ' + negative['Item'].astype(str))))} "
        "-> rejected in the curated layer and listed in outputs/reports/faostat_rejected_rows.csv.",
        f"7. **Duplicate keys** (area, item, element, source, year): {duplicates}.",
        "8. **M49 codes** are stored as text with a leading apostrophe (`'608`) -> cleaned in staging.",
    ]
    out = OUT_DIR / "faostat_profile.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    for report in (profile_edgar(), profile_worldbank(), profile_faostat()):
        print(f"Wrote {report}")
