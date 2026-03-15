````markdown
# CM3070 Final Project – SG Course Recommender

This project is a data-driven personalised educational content recommendation system focused on Singapore post-secondary courses. It allows users to search, filter, and explore courses through a web interface, with recommendations and course data served by a FastAPI backend.

## Project Structure

```text
FINAL_PRODUCT/
│
├── backend/
│   ├── __pycache__/
│   ├── .venv/
│   ├── data/
│   │   ├── app.db
│   │   ├── courses_clean.csv
│   │   ├── courses.csv
│   │   └── data_quality_report.csv
│   ├── tools/
│   │   ├── clean_courses.py
│   │   ├── standardise_institutions.py
│   │   └── update_data.py
│   ├── db.py
│   ├── main.py
│   └── requirements.txt
│
├── frontend/
│   ├── app.js
│   ├── index.html
│   └── styles.css
│
└── README.md
````

## Features

* Keyword-based course search
* Filtering by selected course attributes
* Personalised educational content recommendation
* Dataset cleaning and update pipeline
* FastAPI backend API
* Frontend interface for browsing and comparing courses

## Requirements

* Python 3
* A virtual environment set up in `backend/.venv`
* Required Python packages installed from `backend/requirements.txt`

## How to Run the Backend

```bash
cd ~/Desktop/Final_product/backend
source .venv/bin/activate
python3 -m uvicorn main:app --reload --port 8000
```

The backend runs at:

```text
http://127.0.0.1:8000
```

API documentation is available at:

```text
http://localhost:8000/docs
```

## How to Run the Frontend

```bash
cd ~/Desktop/Final_product/frontend
python3 -m http.server 5500
```

The frontend runs at:

```text
http://localhost:5500/
```

## How to Run the Dataset Update Pipeline

```bash
cd /Users/harneetkaur/Desktop/Final_product/backend
source .venv/bin/activate
python tools/update_data.py
```

This command refreshes and processes the dataset files used by the application.

## Repository Notes

The working project folder includes local development files such as `.venv`, `__pycache__`, and `app.db`. However, these should not be pushed to GitHub. The repository should only contain the source code, dataset files needed for the project, and documentation.

Files and folders that should be excluded from GitHub are handled in `.gitignore`, including:

```text
.env
.DS_Store
backend/data/app.db
backend/.venv/
backend/__pycache__/
```

## Suggested GitHub Upload Contents

The public repository should include:

* `backend/main.py`
* `backend/db.py`
* `backend/requirements.txt`
* `backend/tools/clean_courses.py`
* `backend/tools/standardise_institutions.py`
* `backend/tools/update_data.py`
* `backend/data/courses.csv`
* `backend/data/courses_clean.csv`
* `backend/data/data_quality_report.csv`
* `frontend/app.js`
* `frontend/index.html`
* `frontend/styles.css`
* `README.md`
* `.gitignore`

The repository should not include:

* `backend/.venv/`
* `backend/__pycache__/`
* `backend/data/app.db`

## Author

Harneet Kaur
```
