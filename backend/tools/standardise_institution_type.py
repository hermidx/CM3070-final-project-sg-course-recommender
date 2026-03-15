import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
csv_path = BASE_DIR / "data" / "courses.csv"

df = pd.read_csv(csv_path)

poly_keywords = [
    "ngee ann polytechnic",
    "temasek polytechnic",
    "singapore polytechnic",
    "nanyang polytechnic",
    "republic polytechnic",
]

local_uni_keywords = [
    "national university of singapore",
    "nanyang technological university",
    "singapore management university",
    "singapore university of technology and design",
    "singapore institute of technology",
    "singapore university of social sciences",
    "nus",
    "ntu",
    "smu",
    "sutd",
    "sit",
    "suss",
]

def map_type(inst: str) -> str:
    inst = str(inst).strip().lower()

    if any(k in inst for k in poly_keywords):
        return "Poly"

    if any(k in inst for k in local_uni_keywords):
        return "Local University"

    return "Private University"

df["institution_type"] = df["institution"].apply(map_type)

df.to_csv(csv_path, index=False)
print("Updated institution_type:", csv_path)