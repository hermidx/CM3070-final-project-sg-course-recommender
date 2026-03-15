import re
from pathlib import Path
import pandas as pd
from urllib.parse import urlparse, urlunparse

BASE_DIR = Path(__file__).resolve().parents[1]   # backend/
DATA_DIR = BASE_DIR / "data"
IN_PATH = DATA_DIR / "courses.csv"
OUT_PATH = DATA_DIR / "courses_clean.csv"
REPORT_PATH = DATA_DIR / "data_quality_report.csv"

EXPECTED_COLS = [
    "course_name",
    "institution",
    "institution_type",
    "level",
    "skills",
    "description",
    "url",
    "duration",
    "fees",
    "prerequisites",
    "entry_requirements",
]


def norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip())


def strip_wrapping_quotes(s: str) -> str:
    s = norm_space(s)
    return s.strip('"').strip("'").strip()


def clean_url(u: str) -> str:
    u = str(u).strip()
    if not u:
        return ""
    if not u.startswith(("http://", "https://")):
        return ""
    try:
        p = urlparse(u)
        p = p._replace(fragment="")
        return urlunparse(p)
    except Exception:
        return ""


def main():
    df = pd.read_csv(IN_PATH)

    for col in EXPECTED_COLS:
        if col not in df.columns:
            df[col] = ""

    df = df[EXPECTED_COLS].copy()

    for c in df.columns:
        df[c] = df[c].fillna("").astype(str).map(strip_wrapping_quotes)

    df["url_raw"] = df["url"]
    df["url"] = df["url"].map(clean_url)
    df["url_invalid"] = df["url"].eq("")
    df["url_duplicate"] = df["url"].ne("") & df["url"].duplicated(keep="first")

    institution_map = {
        "Republic Polytechnic (RP)": "Republic Polytechnic",
        'Singapore University of Social Sciences"': "Singapore University of Social Sciences",
        "Singapore University Of Social Sciences": "Singapore University of Social Sciences",
    }

    df["institution"] = df["institution"].replace(institution_map)
    df["institution"] = df["institution"].map(norm_space)

    df["institution_type"] = df["institution_type"].map(norm_space)

    institution_type_map = {
        "Poly": "Polytechnic",
        "poly": "Polytechnic",
        "POLY": "Polytechnic",
        "LocalUniversity": "Local University",
        "Localuniversity": "Local University",
        "Private Education Institution": "Private University",
        "Private education institution": "Private University",
        "Private education institution ": "Private University",
        "Private University ": "Private University",
        "Nanyang Technological University": "Local University",
        "Singapore University Of Social Sciences": "Local University",
        "Singapore University of Social Sciences": "Local University",
    }

    df["institution_type"] = df["institution_type"].replace(institution_type_map)
    df["level"] = df["level"].map(norm_space)

    for c in EXPECTED_COLS:
        df[c] = df[c].replace("", "Nil")

    report = pd.DataFrame({
        "metric": [
            "rows_total",
            "url_invalid_count",
            "url_duplicate_count",
            "missing_course_name_count",
            "missing_institution_count",
            "missing_description_count",
            "missing_fees_count",
            "missing_entry_requirements_count",
        ],
        "value": [
            len(df),
            int(df["url_invalid"].sum()),
            int(df["url_duplicate"].sum()),
            int((df["course_name"] == "Nil").sum()),
            int((df["institution"] == "Nil").sum()),
            int((df["description"] == "Nil").sum()),
            int((df["fees"] == "Nil").sum()),
            int((df["entry_requirements"] == "Nil").sum()),
        ]
    })

    df.to_csv(OUT_PATH, index=False)
    report.to_csv(REPORT_PATH, index=False)

    print(f"✅ Saved cleaned dataset: {OUT_PATH}")
    print(f"✅ Saved quality report:  {REPORT_PATH}")


if __name__ == "__main__":
    main()