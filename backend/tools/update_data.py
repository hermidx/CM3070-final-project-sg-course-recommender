from pathlib import Path
import subprocess
import sys

BASE = Path(__file__).resolve().parents[1]   # backend/
TOOLS = BASE / "tools"


def main():
    print("Refreshing dataset from courses.csv...")
    subprocess.check_call([sys.executable, str(TOOLS / "clean_courses.py")])
    print("✅ Dataset refresh complete.")


if __name__ == "__main__":
    main()