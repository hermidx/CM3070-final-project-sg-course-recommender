import os
import re
import hashlib
from pathlib import Path
from typing import Dict, Tuple, Any, List, Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# ✅ SQLite helpers
from db import init_db, get_conn

# -------------------------
# Config
# -------------------------
API_TITLE = os.getenv("API_TITLE", "SG Course Recommender API")
SEMANTIC_MODEL_NAME = os.getenv("SEMANTIC_MODEL_NAME", "all-MiniLM-L6-v2")
ENABLE_SEMANTIC = os.getenv("ENABLE_SEMANTIC", "true").lower() == "true"
TOP_K_MAX = int(os.getenv("TOP_K_MAX", "20"))

ALLOWED_ORIGINS = [
    x.strip()
    for x in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5500,http://127.0.0.1:5500",
    ).split(",")
    if x.strip()
]

# --- Paths / config ---
BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "data" / "courses_clean.csv"
if not CSV_PATH.exists():
    CSV_PATH = BASE_DIR / "data" / "courses.csv"

REQUIRED_COLS = [
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

# --- Caches / models ---
TFIDF_CACHE: Dict[Tuple[str, str, str, bool, bool], Dict[str, Any]] = {}
EMBED_CACHE: Dict[Tuple[str, str, str, bool, bool], Dict[str, Any]] = {}

SEMANTIC_MODEL = None
SEMANTIC_AVAILABLE = False
SEMANTIC_ERROR = None

if ENABLE_SEMANTIC:
    try:
        SEMANTIC_MODEL = SentenceTransformer(SEMANTIC_MODEL_NAME)
        SEMANTIC_AVAILABLE = True
    except Exception as e:
        SEMANTIC_MODEL = None
        SEMANTIC_AVAILABLE = False
        SEMANTIC_ERROR = str(e)

app = FastAPI(title=API_TITLE)


@app.on_event("startup")
def _startup():
    init_db()

    if not CSV_PATH.exists():
        raise RuntimeError(f"Dataset file not found: {CSV_PATH}")

    if df.empty:
        raise RuntimeError("Dataset loaded successfully but contains 0 rows.")


# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SYNONYMS = {
    "ai": "artificial intelligence machine learning",
    "ml": "machine learning artificial intelligence",
    "ds": "data science data analytics",
    "data analytics": "data analytics business analytics data analysis",
    "business analytics": "business analytics data analytics decision making",
    "ui ux": "user interface user experience interaction design product design",
    "ux": "user experience interaction design usability",
    "ui": "user interface interface design",
    "fintech": "financial technology digital banking payments",
    "cyber": "cybersecurity information security network security",
    "software eng": "software engineering software development programming",
    "comp sci": "computer science computing programming software",
}


def clean_text(s: str) -> str:
    if s is None:
        return ""
    s = str(s).lower()
    s = re.sub(r"http\S+|www\.\S+", " ", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def expand_query(q: str) -> str:
    q_clean = clean_text(q)
    for k in sorted(SYNONYMS.keys(), key=len, reverse=True):
        q_clean = re.sub(rf"\b{re.escape(k)}\b", SYNONYMS[k], q_clean)
    return q_clean


def build_corpus(df_: pd.DataFrame) -> pd.Series:
    title = df_["course_name"].fillna("").astype(str)
    skills = df_["skills"].fillna("").astype(str)
    desc = df_["description"].fillna("").astype(str)
    level = df_["level"].fillna("").astype(str)
    institution = df_["institution"].fillna("").astype(str)
    prereq = df_["prerequisites"].fillna("").astype(str)

    weighted = (
        (title + " ") * 3 +
        (skills + " ") * 2 +
        (level + " ") * 1 +
        (institution + " ") * 1 +
        (prereq + " ") * 1 +
        (desc + " ") * 1
    )

    return weighted.apply(clean_text)


def make_course_id(row) -> str:
    base = (
        f"{str(row.get('course_name','')).strip()}|"
        f"{str(row.get('institution','')).strip()}|"
        f"{str(row.get('url','')).strip()}"
    )
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]


def normalise_scores(arr: np.ndarray) -> np.ndarray:
    arr = np.asarray(arr, dtype=float)
    if arr.size == 0:
        return arr
    mn = arr.min()
    mx = arr.max()
    if mx - mn < 1e-9:
        return np.zeros_like(arr)
    return (arr - mn) / (mx - mn + 1e-9)


def get_user_profile_course_ids(user_id: str, limit: int = 100) -> Dict[str, float]:
    """
    Build weighted user preference signals from multiple behaviour sources.
    Positive weights boost recommendations.
    Negative weights suppress recommendations.
    """
    if not user_id or not user_id.strip():
        return {}

    uid = user_id.strip()
    conn = get_conn()

    weights: Dict[str, float] = {}

    rows = conn.execute(
        """
        SELECT course_id, event_type
        FROM events
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (uid, limit),
    ).fetchall()

    for r in rows:
        cid = r["course_id"]
        et = (r["event_type"] or "").strip().lower()
        if not cid:
            continue

        if et == "like":
            weights[cid] = weights.get(cid, 0.0) + 3.0
        elif et == "save":
            weights[cid] = weights.get(cid, 0.0) + 2.0
        elif et == "click":
            weights[cid] = weights.get(cid, 0.0) + 1.0

    fb_rows = conn.execute(
        """
        SELECT course_id, rating
        FROM feedback
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (uid, limit),
    ).fetchall()

    for r in fb_rows:
        cid = r["course_id"]
        rating = int(r["rating"])
        if not cid:
            continue

        if rating == 1:
            weights[cid] = weights.get(cid, 0.0) + 4.0
        elif rating == -1:
            weights[cid] = weights.get(cid, 0.0) - 4.0

    saved_rows = conn.execute(
        """
        SELECT course_id
        FROM saved_courses
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (uid, limit),
    ).fetchall()

    conn.close()

    for r in saved_rows:
        cid = r["course_id"]
        if cid:
            weights[cid] = weights.get(cid, 0.0) + 2.5

    return weights


def get_weighted_profile_indices(
    course_weights: Dict[str, float],
    scoped_df: pd.DataFrame
) -> Tuple[List[int], List[float], List[int]]:
    """
    Map weighted course_ids to positions in the current scoped dataframe.
    Returns:
      - positive indices
      - positive weights
      - negative indices
    """
    if not course_weights:
        return [], [], []

    idxs_pos: List[int] = []
    wts_pos: List[float] = []
    idxs_neg: List[int] = []

    cid_to_idx = {cid: i for i, cid in enumerate(scoped_df["course_id"].tolist())}

    for cid, wt in course_weights.items():
        idx = cid_to_idx.get(cid)
        if idx is None:
            continue

        if wt > 0:
            idxs_pos.append(idx)
            wts_pos.append(float(wt))
        elif wt < 0:
            idxs_neg.append(idx)

    return idxs_pos, wts_pos, idxs_neg


def extract_why_matched(query: str, row: pd.Series, top_n: int = 5) -> List[str]:
    query_terms = set(clean_text(expand_query(query)).split())

    row_terms = set()
    for field in ["course_name", "skills", "description", "prerequisites"]:
        row_terms.update(clean_text(row.get(field, "")).split())

    overlap = [t for t in query_terms if t in row_terms and len(t) > 2]

    skill_text = clean_text(row.get("skills", ""))
    skill_terms = [t for t in skill_text.split() if len(t) > 2]

    combined = []
    for term in overlap + skill_terms:
        if term not in combined:
            combined.append(term)

    return combined[:top_n]


def missing_fields(row: pd.Series) -> List[str]:
    fields = []
    for label, col in [
        ("fees", "fees"),
        ("duration", "duration"),
        ("prerequisites", "prerequisites"),
        ("entry requirements", "entry_requirements"),
    ]:
        val = str(row.get(col, "")).strip().lower()
        if val in ("", "nil", "n/a", "na", "none"):
            fields.append(label)
    return fields


# --- Load dataset ---
df = pd.read_csv(CSV_PATH)

for c in REQUIRED_COLS:
    if c not in df.columns:
        df[c] = "Nil"

for c in REQUIRED_COLS:
    df[c] = df[c].fillna("Nil").astype(str)

for c in ["duration", "fees", "prerequisites", "entry_requirements"]:
    df[c] = df[c].apply(lambda x: "Nil" if not str(x).strip() else str(x).strip())

if "course_id" not in df.columns:
    df["course_id"] = df.apply(make_course_id, axis=1)

df["combined_text"] = build_corpus(df)


# -------------------------
# Models
# -------------------------
class SearchRequest(BaseModel):
    query: str
    user_id: Optional[str] = None

    institution_type: Optional[str] = None
    level: Optional[str] = None
    institution: Optional[str] = None
    top_k: int = 10

    use_semantic: bool = False
    hybrid: bool = False

    requires_math: bool = False
    requires_english: bool = False


class SaveReq(BaseModel):
    user_id: str
    course_id: str


class SavedDetailsReq(BaseModel):
    course_ids: List[str]


class RemoveSavedReq(BaseModel):
    user_id: str
    course_id: str


class FeedbackReq(BaseModel):
    user_id: str
    course_id: str
    rating: int
    comment: str = ""


class EventReq(BaseModel):
    user_id: str
    course_id: str
    event_type: str
    query: str = ""


# -------------------------
# Basic routes
# -------------------------
@app.get("/")
def root():
    return {
        "status": "ok",
        "docs": "/docs",
        "endpoints": [
            "/health",
            "/api/meta",
            "/api/search",
            "/user/save",
            "/user/saved",
            "/user/saved/details (GET user_id or POST course_ids)",
            "/user/saved/remove",
            "/user/saved/clear (optional)",
            "/feedback",
            "/events",
            "/admin/cache/clear",
        ],
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "dataset_path": str(CSV_PATH),
        "dataset_rows": int(len(df)),
        "semantic_enabled": ENABLE_SEMANTIC,
        "semantic_available": SEMANTIC_AVAILABLE,
        "semantic_error": SEMANTIC_ERROR,
        "tfidf_cache_entries": len(TFIDF_CACHE),
        "embed_cache_entries": len(EMBED_CACHE),
    }


@app.post("/admin/cache/clear")
def clear_caches():
    TFIDF_CACHE.clear()
    EMBED_CACHE.clear()
    return {"status": "ok", "message": "Caches cleared"}


@app.get("/api/meta")
def meta():
    return {
        "institution_types": sorted([x for x in df["institution_type"].unique() if x.strip()]),
        "levels": sorted([x for x in df["level"].unique() if x.strip()]),
        "institutions": sorted([x for x in df["institution"].unique() if x.strip()]),
    }


# -------------------------
# Search
# -------------------------
@app.post("/api/search")
def search(req: SearchRequest):
    try:
        if not req.query or not req.query.strip():
            return {"results": [], "message": "Empty query"}

        query_text = req.query.strip()
        if len(query_text) > 200:
            raise HTTPException(status_code=400, detail="Query too long. Please keep it under 200 characters.")

        top_k = max(1, min(int(req.top_k), TOP_K_MAX))

        if req.hybrid and not req.use_semantic:
            raise HTTPException(status_code=400, detail="Hybrid mode requires semantic mode to be enabled.")

        if req.use_semantic and not SEMANTIC_AVAILABLE:
            return {
                "results": [],
                "message": "Semantic mode is currently unavailable on this server.",
                "detail": SEMANTIC_ERROR or "Semantic model failed to load.",
            }

        scoped = df

        def is_all(v: Optional[str]) -> bool:
            return v is None or v.strip().lower() == "all"

        if not is_all(req.institution_type):
            scoped = scoped[scoped["institution_type"] == req.institution_type]
        if not is_all(req.level):
            scoped = scoped[scoped["level"] == req.level]
        if not is_all(req.institution):
            scoped = scoped[scoped["institution"] == req.institution]

        if req.requires_math and "entry_requirements" in scoped.columns:
            scoped = scoped[
                scoped["entry_requirements"].str.contains(
                    r"\b(math|mathematics)\b", case=False, na=False, regex=True
                )
            ]
        if req.requires_english and "entry_requirements" in scoped.columns:
            scoped = scoped[
                scoped["entry_requirements"].str.contains(
                    r"\benglish\b", case=False, na=False, regex=True
                )
            ]

        if scoped.empty:
            return {"results": [], "message": "No courses match the selected filters"}

        key = (
            (req.institution_type or "All").strip(),
            (req.level or "All").strip(),
            (req.institution or "All").strip(),
            bool(req.requires_math),
            bool(req.requires_english),
        )

        # -----------------------------
        # Semantic / Hybrid branch
        # -----------------------------
        if req.use_semantic:
            cached_sem = EMBED_CACHE.get(key)

            if cached_sem is None:
                scoped_reset = scoped.reset_index(drop=True)
                doc_emb = SEMANTIC_MODEL.encode(
                    scoped_reset["combined_text"].tolist(),
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
                cached_sem = {"scoped": scoped_reset, "doc_emb": doc_emb}
                EMBED_CACHE[key] = cached_sem

            scoped_sem = cached_sem["scoped"]
            doc_emb = cached_sem["doc_emb"]

            expanded_query = expand_query(query_text)

            q_emb = SEMANTIC_MODEL.encode(
                [expanded_query],
                normalize_embeddings=True,
                show_progress_bar=False,
            )[0]

            sem_sims = np.dot(doc_emb, q_emb)
            final_sims = sem_sims.copy()

            if req.user_id and req.user_id.strip():
                course_weights = get_user_profile_course_ids(req.user_id.strip(), limit=100)
                idxs_pos, wts_pos, idxs_neg = get_weighted_profile_indices(course_weights, scoped_sem)

                if idxs_pos:
                    pos_embs = doc_emb[idxs_pos]
                    wts = np.asarray(wts_pos, dtype=float)
                    wts = wts / (wts.sum() + 1e-9)

                    user_profile_emb = np.average(pos_embs, axis=0, weights=wts)
                    user_profile_emb = user_profile_emb / (np.linalg.norm(user_profile_emb) + 1e-9)

                    profile_sims = np.dot(doc_emb, user_profile_emb)

                    sem_norm = normalise_scores(final_sims)
                    profile_norm = normalise_scores(profile_sims)

                    final_sims = 0.70 * sem_norm + 0.30 * profile_norm

                if idxs_neg:
                    final_sims[idxs_neg] = final_sims[idxs_neg] * 0.65

            if req.hybrid:
                cached_tfidf = TFIDF_CACHE.get(key)
                if cached_tfidf is None:
                    vectorizer_h = TfidfVectorizer(
                        stop_words="english",
                        ngram_range=(1, 2),
                        min_df=1,
                        sublinear_tf=True,
                    )
                    tfidf_matrix_h = vectorizer_h.fit_transform(scoped_sem["combined_text"])
                    cached_tfidf = {
                        "vectorizer": vectorizer_h,
                        "tfidf_matrix": tfidf_matrix_h,
                        "scoped": scoped_sem,
                    }
                    TFIDF_CACHE[key] = cached_tfidf

                vectorizer_h = cached_tfidf["vectorizer"]
                tfidf_matrix_h = cached_tfidf["tfidf_matrix"]

                q_vec_h = vectorizer_h.transform([expanded_query])
                tf_sims = cosine_similarity(q_vec_h, tfidf_matrix_h).ravel()

                sem_norm = normalise_scores(final_sims)
                tf_norm = normalise_scores(tf_sims)

                query_clean = clean_text(query_text)
                short_query = len(query_clean.split()) <= 2

                if short_query:
                    final_sims = 0.55 * sem_norm + 0.45 * tf_norm
                else:
                    final_sims = 0.70 * sem_norm + 0.30 * tf_norm

            ranked_idx = final_sims.argsort()[::-1]

            recs = scoped_sem.iloc[ranked_idx].copy()
            recs["similarity"] = final_sims[ranked_idx]

            threshold = 0.12 if req.hybrid else 0.15
            recs = recs[recs["similarity"] > threshold]

            if recs.empty:
                return {"results": [], "message": "No close matches"}

            max_sim = recs["similarity"].max()
            recs["match_pct"] = (recs["similarity"] / (max_sim + 1e-9) * 100).round(1)
            recs = recs.head(top_k)

            results = []
            for _, r in recs.iterrows():
                desc = str(r.get("description", ""))
                results.append(
                    {
                        "course_id": r.get("course_id", ""),
                        "course_name": r.get("course_name", "Nil"),
                        "institution": r.get("institution", "Nil"),
                        "institution_type": r.get("institution_type", "Nil"),
                        "level": r.get("level", "Nil"),
                        "skills": r.get("skills", "Nil"),
                        "description": (desc[:260] + "…") if len(desc) > 260 else desc,
                        "url": r.get("url", ""),
                        "duration": r.get("duration", "Nil"),
                        "fees": r.get("fees", "Nil"),
                        "prerequisites": r.get("prerequisites", "Nil"),
                        "entry_requirements": r.get("entry_requirements", "Nil"),
                        "match_score": round(float(r["match_pct"]), 1),
                        "why_matched": extract_why_matched(query_text, r),
                        "missing_fields": missing_fields(r),
                        "mode_used": "hybrid" if req.hybrid else "semantic",
                    }
                )

            mode_label = "Hybrid" if req.hybrid else "Semantic"
            return {
                "results": results,
                "note": f"{mode_label} match score = relative similarity within this search (not probability/accuracy). Personalisation is applied when user history exists.",
                "ui_meta": {
                    "query": query_text,
                    "result_count": len(results),
                    "mode": mode_label.lower(),
                    "personalised": bool(req.user_id and req.user_id.strip()),
                },
            }

        # -----------------------------
        # TF-IDF branch
        # -----------------------------
        cached = TFIDF_CACHE.get(key)
        if cached is None:
            vectorizer = TfidfVectorizer(
                stop_words="english",
                ngram_range=(1, 2),
                min_df=1,
                sublinear_tf=True,
            )
            tfidf_matrix = vectorizer.fit_transform(scoped["combined_text"])
            cached = {
                "vectorizer": vectorizer,
                "tfidf_matrix": tfidf_matrix,
                "scoped": scoped.reset_index(drop=True),
            }
            TFIDF_CACHE[key] = cached

        vectorizer = cached["vectorizer"]
        tfidf_matrix = cached["tfidf_matrix"]
        scoped_tfidf = cached["scoped"]

        q_vec = vectorizer.transform([expand_query(query_text)])
        sims = cosine_similarity(q_vec, tfidf_matrix).ravel()

        if req.user_id and req.user_id.strip():
            course_weights = get_user_profile_course_ids(req.user_id.strip(), limit=100)
            idxs_pos, wts_pos, idxs_neg = get_weighted_profile_indices(course_weights, scoped_tfidf)

            if idxs_pos:
                pos_mat = tfidf_matrix[idxs_pos]
                wts = np.asarray(wts_pos, dtype=float)
                wts = wts / (wts.sum() + 1e-9)

                user_profile_vec = np.average(pos_mat.toarray(), axis=0, weights=wts).reshape(1, -1)
                user_sims = cosine_similarity(user_profile_vec, tfidf_matrix).ravel()

                sims_norm = normalise_scores(sims)
                user_norm = normalise_scores(user_sims)

                sims = 0.70 * sims_norm + 0.30 * user_norm

            if idxs_neg:
                neg_mask = np.zeros_like(sims, dtype=bool)
                neg_mask[idxs_neg] = True
                sims[neg_mask] = sims[neg_mask] * 0.65

        ranked_idx = sims.argsort()[::-1]
        recs = scoped_tfidf.iloc[ranked_idx].copy()
        recs["similarity"] = sims[ranked_idx]
        recs = recs[recs["similarity"] > 0]

        if recs.empty:
            return {"results": [], "message": "No close matches"}

        max_sim = recs["similarity"].max()
        recs["match_pct"] = (recs["similarity"] / (max_sim + 1e-9) * 100).round(1)
        recs = recs.head(top_k)

        results = []
        for _, r in recs.iterrows():
            desc = str(r.get("description", ""))
            results.append(
                {
                    "course_id": r.get("course_id", ""),
                    "course_name": r.get("course_name", "Nil"),
                    "institution": r.get("institution", "Nil"),
                    "institution_type": r.get("institution_type", "Nil"),
                    "level": r.get("level", "Nil"),
                    "skills": r.get("skills", "Nil"),
                    "description": (desc[:260] + "…") if len(desc) > 260 else desc,
                    "url": r.get("url", ""),
                    "duration": r.get("duration", "Nil"),
                    "fees": r.get("fees", "Nil"),
                    "prerequisites": r.get("prerequisites", "Nil"),
                    "entry_requirements": r.get("entry_requirements", "Nil"),
                    "match_score": round(float(r["match_pct"]), 1),
                    "why_matched": extract_why_matched(query_text, r),
                    "missing_fields": missing_fields(r),
                    "mode_used": "tfidf",
                }
            )

        return {
            "results": results,
            "note": "Match score = relative similarity within this search (not probability/accuracy). Personalisation is applied when user history exists.",
            "ui_meta": {
                "query": query_text,
                "result_count": len(results),
                "mode": "tfidf",
                "personalised": bool(req.user_id and req.user_id.strip()),
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


# ==========================
# ✅ Events (SQLite)
# ==========================
@app.post("/events")
def log_event(req: EventReq):
    et = (req.event_type or "").strip().lower()
    if et not in ("click", "save", "like"):
        return {"status": "error", "message": "event_type must be click | save | like"}

    if not req.user_id or not req.user_id.strip():
        return {"status": "error", "message": "user_id is required"}

    if not req.course_id or not req.course_id.strip():
        return {"status": "error", "message": "course_id is required"}

    conn = get_conn()
    conn.execute(
        "INSERT INTO events(user_id, course_id, event_type, query) VALUES (?,?,?,?)",
        (req.user_id.strip(), req.course_id.strip(), et, (req.query or "").strip()),
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}


# ==========================
# ✅ Feedback (SQLite)
# ==========================
@app.post("/feedback")
def give_feedback(req: FeedbackReq):
    rating = int(req.rating)
    if rating not in (1, -1):
        return {"status": "error", "message": "rating must be +1 or -1"}

    if not req.user_id or not req.user_id.strip():
        return {"status": "error", "message": "user_id is required"}

    if not req.course_id or not req.course_id.strip():
        return {"status": "error", "message": "course_id is required"}

    conn = get_conn()
    conn.execute(
        "INSERT INTO feedback(user_id, course_id, rating, comment) VALUES (?,?,?,?)",
        (req.user_id.strip(), req.course_id.strip(), rating, (req.comment or "").strip()),
    )

    if rating == 1:
        conn.execute(
            "INSERT INTO events(user_id, course_id, event_type, query) VALUES (?,?,?,?)",
            (req.user_id.strip(), req.course_id.strip(), "like", ""),
        )

    conn.commit()
    conn.close()
    return {"status": "ok"}


# ==========================
# ✅ Saved courses (SQLite)
# ==========================
@app.post("/user/save")
def save_course(req: SaveReq):
    if not req.user_id or not req.user_id.strip():
        return {"status": "error", "message": "user_id is required"}

    if not req.course_id or not req.course_id.strip():
        return {"status": "error", "message": "course_id is required"}

    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO saved_courses(user_id, course_id) VALUES (?,?)",
        (req.user_id.strip(), req.course_id.strip()),
    )

    conn.execute(
        "INSERT INTO events(user_id, course_id, event_type, query) VALUES (?,?,?,?)",
        (req.user_id.strip(), req.course_id.strip(), "save", ""),
    )

    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.get("/user/saved")
def get_saved(user_id: str):
    if not user_id or not user_id.strip():
        return {"saved": []}

    conn = get_conn()
    rows = conn.execute(
        "SELECT course_id FROM saved_courses WHERE user_id=? ORDER BY created_at DESC",
        (user_id.strip(),),
    ).fetchall()
    conn.close()
    return {"saved": [r["course_id"] for r in rows]}


@app.get("/user/saved/details")
def saved_details_get(user_id: str = Query(...)):
    if not user_id or not user_id.strip():
        return {"results": []}

    conn = get_conn()
    rows = conn.execute(
        "SELECT course_id FROM saved_courses WHERE user_id=? ORDER BY created_at DESC",
        (user_id.strip(),),
    ).fetchall()
    conn.close()
    ids = [r["course_id"] for r in rows]
    return _details_from_ids(ids)


@app.post("/user/saved/details")
def saved_details_post(req: SavedDetailsReq):
    return _details_from_ids(req.course_ids or [])


def _details_from_ids(course_ids: List[str]):
    if not course_ids:
        return {"results": []}

    ordered_ids = [x.strip() for x in course_ids if x and x.strip()]
    if not ordered_ids:
        return {"results": []}

    ids_set = set(ordered_ids)
    matched = df[df["course_id"].isin(ids_set)].copy()
    if matched.empty:
        return {"results": []}

    order_index = {cid: i for i, cid in enumerate(ordered_ids)}
    matched["_order"] = matched["course_id"].map(order_index).fillna(10**9).astype(int)
    matched = matched.sort_values("_order").drop(columns=["_order"])

    results = []
    for _, r in matched.iterrows():
        desc = str(r.get("description", ""))
        results.append(
            {
                "course_id": r.get("course_id", ""),
                "course_name": r.get("course_name", "Nil"),
                "institution": r.get("institution", "Nil"),
                "institution_type": r.get("institution_type", "Nil"),
                "level": r.get("level", "Nil"),
                "skills": r.get("skills", "Nil"),
                "description": (desc[:260] + "…") if len(desc) > 260 else desc,
                "url": r.get("url", ""),
                "duration": r.get("duration", "Nil"),
                "fees": r.get("fees", "Nil"),
                "prerequisites": r.get("prerequisites", "Nil"),
                "entry_requirements": r.get("entry_requirements", "Nil"),
                "why_matched": [],
                "missing_fields": missing_fields(r),
                "mode_used": "saved",
            }
        )

    return {"results": results}


@app.post("/user/saved/remove")
def remove_saved(req: RemoveSavedReq):
    if not req.user_id or not req.user_id.strip():
        return {"status": "error", "message": "user_id is required"}

    if not req.course_id or not req.course_id.strip():
        return {"status": "error", "message": "course_id is required"}

    conn = get_conn()
    conn.execute(
        "DELETE FROM saved_courses WHERE user_id=? AND course_id=?",
        (req.user_id.strip(), req.course_id.strip()),
    )
    conn.commit()
    conn.close()
    return {"status": "ok", "removed": req.course_id}


@app.delete("/user/saved/clear")
def clear_saved(user_id: str = Query(...)):
    if not user_id or not user_id.strip():
        return {"status": "error", "message": "user_id is required"}

    conn = get_conn()
    conn.execute("DELETE FROM saved_courses WHERE user_id=?", (user_id.strip(),))
    conn.commit()
    conn.close()
    return {"status": "ok", "cleared_for": user_id}