import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
csv_path = BASE_DIR / "data" / "courses.csv"

df = pd.read_csv(csv_path)

poly = {
    "Ngee Ann Polytechnic",
    "Temasek Polytechnic",
    "Singapore Polytechnic",
    "Nanyang Polytechnic",
    "Republic Polytechnic",
}
local_uni = {"NUS", "NTU", "SMU", "SUTD", "SIT", "SUSS"}

def map_type(inst: str) -> str:
    inst = str(inst).strip()
    if inst in poly:
        return "Poly"
    if inst in local_uni:
        return "Local University"
    return "Private University"

df["institution_type"] = df["institution"].apply(map_type)

df.to_csv(csv_path, index=False)
print("Updated institution_type:", csv_path)
