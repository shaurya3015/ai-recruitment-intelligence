import re
from datetime import datetime
from models import SessionLocal, Resume, CandidateScore

# ── Skill vocabulary ─────────────────────────────────────────────────────────
TECHNICAL_SKILLS = {
    'python', 'java', 'javascript', 'c++', 'c#', 'sql', 'react', 'angular', 'aws', 'gcp',
    'docker', 'kubernetes', 'tensorflow', 'pytorch', 'machine learning', 'data science',
    'nlp', 'computer vision', 'fastapi', 'django', 'nodejs', 'typescript', 'git',
    'html', 'css', 'php', 'ruby', 'go', 'rust', 'scala', 'r programming'
}

SOFT_SKILLS = {
    'leadership', 'communication', 'teamwork', 'problem solving', 'critical thinking',
    'project management', 'agile', 'scrum', 'presentations', 'mentoring', 'collaboration',
    'time management', 'adaptability', 'negotiation', 'conflict resolution'
}

# Education levels already expressed on a 0–100 scale (broadened to cover common
# abbreviations so real degrees stop falling through to 0).
EDUCATION_KEYWORDS = {
    'phd': 100, 'ph.d': 100, 'doctorate': 100,
    'masters': 80, 'master': 80, 'm.tech': 80, 'mtech': 80, 'm.e': 80,
    'msc': 78, 'm.sc': 78, 'mca': 76, 'mba': 76,
    'bachelors': 60, 'bachelor': 60, 'b.tech': 60, 'btech': 60, 'b.e': 58,
    'bsc': 56, 'b.sc': 56, 'bca': 54,
    'computer science': 65, 'engineering': 60, 'data science': 65,
    'information technology': 60, 'business': 45,
    'diploma': 40, 'high school': 20,
}

# ── Job-family skill profiles ────────────────────────────────────────────────
# job_title is substring-matched against these keys; matching profiles define the
# set of skills that are *relevant* to that search. This is what makes ranking
# job-aware instead of a fixed global skill count.
AI_ML_SKILLS = {
    'python', 'pytorch', 'tensorflow', 'keras', 'scikit-learn', 'sklearn',
    'machine learning', 'deep learning', 'neural network', 'cnn', 'rnn', 'lstm',
    'transformer', 'transformers', 'nlp', 'natural language processing',
    'computer vision', 'opencv', 'llm', 'large language model', 'rag', 'langchain',
    'llama', 'huggingface', 'hugging face', 'mlops', 'qdrant', 'vector database',
    'faiss', 'embedding', 'embeddings', 'data science', 'pandas', 'numpy',
    'matplotlib', 'scipy', 'seaborn', 'fine-tuning', 'fine tuning', 'yolo', 'bert',
    'gpt', 'diffusion', 'reinforcement learning', 'feature engineering',
    'model deployment',
}
BACKEND_SKILLS = {
    'python', 'java', 'go', 'node', 'nodejs', 'express', 'django', 'flask', 'fastapi',
    'sql', 'postgres', 'postgresql', 'mysql', 'mongodb', 'redis', 'docker', 'kubernetes',
    'aws', 'gcp', 'microservices', 'rest', 'graphql', 'git', 'c++', 'c#', '.net', 'spring',
}
FRONTEND_SKILLS = {
    'javascript', 'typescript', 'react', 'angular', 'vue', 'html', 'css', 'tailwind',
    'redux', 'next.js', 'webpack', 'figma', 'sass',
}
DATA_ENG_SKILLS = {
    'python', 'sql', 'spark', 'hadoop', 'airflow', 'kafka', 'etl', 'snowflake', 'dbt',
    'bigquery', 'redshift', 'databricks', 'pandas', 'aws', 'gcp',
}
DEVOPS_SKILLS = {
    'docker', 'kubernetes', 'aws', 'gcp', 'azure', 'terraform', 'ci/cd', 'jenkins',
    'ansible', 'linux', 'prometheus', 'grafana',
}

JOB_SKILL_PROFILES = {
    'ai': AI_ML_SKILLS, 'a.i': AI_ML_SKILLS, 'ml': AI_ML_SKILLS,
    'machine learning': AI_ML_SKILLS, 'deep learning': AI_ML_SKILLS,
    'data scien': AI_ML_SKILLS, 'data analyst': AI_ML_SKILLS, 'nlp': AI_ML_SKILLS,
    'computer vision': AI_ML_SKILLS, 'llm': AI_ML_SKILLS, 'research': AI_ML_SKILLS,
    'backend': BACKEND_SKILLS, 'back end': BACKEND_SKILLS, 'software': BACKEND_SKILLS,
    'full stack': BACKEND_SKILLS | FRONTEND_SKILLS,
    'fullstack': BACKEND_SKILLS | FRONTEND_SKILLS,
    'frontend': FRONTEND_SKILLS, 'front end': FRONTEND_SKILLS, 'web': FRONTEND_SKILLS,
    'data engineer': DATA_ENG_SKILLS, 'devops': DEVOPS_SKILLS, 'platform': DEVOPS_SKILLS,
}

# Embedding cache + a one-time "embeddings unavailable" warning flag so a missing
# Ollama doesn't spam a warning per candidate (and never silently scores 0).
_embed_cache = {}
_embed_warned = False


def extract_skills(text: str) -> tuple:
    """Generic skill extraction (kept for diagnostics / backward compatibility)."""
    text_lower = text.lower()
    tech_skills = [s for s in TECHNICAL_SKILLS if s in text_lower]
    soft_skills = [s for s in SOFT_SKILLS if s in text_lower]
    score = min((len(tech_skills) * 0.5 + len(soft_skills) * 0.3), 100)
    return tech_skills + soft_skills, score


def relevant_skill_set(job_title: str) -> set:
    """Skills considered relevant to the searched role."""
    jt = (job_title or "").lower().strip()
    relevant = set()
    for key, skills in JOB_SKILL_PROFILES.items():
        if key in jt:
            relevant |= skills
    # Always include any concrete skill named directly in the job title.
    for s in TECHNICAL_SKILLS:
        if s in jt:
            relevant.add(s)
    return relevant


def keyword_relevance(text: str, job_title: str) -> tuple:
    """0–100 score from how many role-relevant skills appear in the resume."""
    text_lower = text.lower()
    relevant = relevant_skill_set(job_title)
    if not relevant:
        # No recognised role → fall back to generic technical-skill density.
        matched = [s for s in TECHNICAL_SKILLS if s in text_lower]
        return min(len(matched) / 8.0 * 100.0, 100.0), matched
    matched = [s for s in relevant if s in text_lower]
    # ~6 strongly-relevant matches saturates to 100.
    return min(len(matched) / 6.0 * 100.0, 100.0), matched


def _cached_embed(s: str):
    key = (s or "")[:4000]
    if key not in _embed_cache:
        from qdrant_manager import _embed
        _embed_cache[key] = _embed(key)
    return _embed_cache[key]


def embedding_relevance(text: str, job_title: str):
    """Semantic similarity (0–100) between the role and the resume.

    Returns None (never 0) if embeddings are unavailable, so callers fall back to
    keyword relevance instead of silently tanking the candidate.
    """
    global _embed_warned
    try:
        import numpy as np
        relevant = relevant_skill_set(job_title)
        query = (job_title or "").strip()
        if relevant:
            query += " " + " ".join(sorted(relevant))
        if not query.strip() or not (text or "").strip():
            return None
        v_job = np.array(_cached_embed(query), dtype=float)
        v_res = np.array(_cached_embed(text), dtype=float)
        denom = (np.linalg.norm(v_job) * np.linalg.norm(v_res)) or 1.0
        cos = float(np.dot(v_job, v_res) / denom)
        # Cosine for this model typically lands ~0.3–0.8; stretch that to 0–100.
        score = (cos - 0.3) / (0.8 - 0.3) * 100.0
        return max(0.0, min(score, 100.0))
    except Exception as e:
        if not _embed_warned:
            print(f"[ranking] embedding relevance unavailable, using keyword-only ({e})")
            _embed_warned = True
        return None


def compute_relevance(text: str, job_title: str) -> tuple:
    """Hybrid relevance: keyword/skill match (primary) + embedding sim (secondary)."""
    kw, matched = keyword_relevance(text, job_title)
    emb = embedding_relevance(text, job_title)
    combined = kw if emb is None else (0.7 * kw + 0.3 * emb)
    return combined, kw, emb, matched


def extract_experience(text: str) -> tuple:
    """Estimate years of experience from explicit mentions and date ranges (0–100)."""
    t = text or ""
    now = datetime.utcnow().year

    # Explicit "N years"/"N+ yrs", but only trust it when experience/work context exists.
    explicit_years = 0
    nums = [int(n) for n in re.findall(r'(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b', t, re.IGNORECASE)]
    if nums and re.search(r'experience|exp\b|professional|work', t, re.IGNORECASE):
        explicit_years = max(nums)

    # Date ranges: 2019-2023, 2019 – Present, Jan 2020 - Dec 2022, 03/2019 to 06/2021.
    range_pat = r'(?:[A-Za-z]{3,9}\.?\s*|\d{1,2}[/\-]\s*)?((?:19|20)\d{2})\s*(?:[-–—]|to)\s*(present|current|now|(?:[A-Za-z]{3,9}\.?\s*|\d{1,2}[/\-]\s*)?((?:19|20)\d{2}))'
    spans = []
    for m in re.finditer(range_pat, t, re.IGNORECASE):
        start = int(m.group(1))
        end_raw = (m.group(2) or "").lower()
        if 'present' in end_raw or 'current' in end_raw or 'now' in end_raw:
            end = now
        elif m.group(3):
            end = int(m.group(3))
        else:
            continue
        if start <= end <= now + 1 and (end - start) <= 50:
            spans.append((start, min(end, now)))

    span_years = 0.0
    if spans:
        spans.sort()
        merged = []
        for s, e in spans:
            if merged and s <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], e))
            else:
                merged.append((s, e))
        span_years = sum(e - s for s, e in merged)

    years = float(max(explicit_years, span_years))
    score = min((years / 10.0) * 100.0, 100.0)
    return years, score


def extract_education(text: str) -> tuple:
    """Highest education level found, already on a 0–100 scale."""
    text_lower = (text or "").lower()
    degrees = []
    score = 0.0
    for keyword, points in EDUCATION_KEYWORDS.items():
        if keyword in text_lower:
            degrees.append(keyword)
            score = max(score, points)
    return degrees, float(score)


def score_resume(resume_id: int, user_id: int, job_title: str = ""):
    """Score a single resume: hybrid job-relevance + experience + education."""
    db = SessionLocal()

    try:
        resume = db.query(Resume).filter(Resume.id == resume_id).first()
        if not resume:
            return None

        file_name = resume.file_name
        text = resume.extracted_text or ""

        relevance, kw, emb, matched = compute_relevance(text, job_title)
        years, experience_score = extract_experience(text)
        degrees, education_score = extract_education(text)

        # Every component is now 0–100. Job-relevance (skills fit) dominates, then
        # experience, then education as a tie-breaker.
        overall_score = relevance * 0.5 + experience_score * 0.3 + education_score * 0.2

        emb_str = "n/a" if emb is None else f"{emb:5.1f}"
        print(
            f"[rank] {file_name[:30]:30s} | relevance={relevance:5.1f} "
            f"(kw={kw:5.1f} emb={emb_str} matched={len(matched)}) | "
            f"exp={experience_score:5.1f} ({years:.1f}y) | edu={education_score:5.1f} "
            f"| OVERALL={overall_score:5.1f}"
        )

        return {
            "resume_id": resume_id,
            "file_name": file_name,
            "skills": matched,
            "skills_match": round(relevance, 2),
            "experience_match": round(experience_score, 2),
            "education_match": round(education_score, 2),
            "overall_score": round(overall_score, 2),
        }
    finally:
        db.close()


def rank_candidates(user_id: int, job_title: str = ""):
    """Score and rank all candidates for a user."""
    db = SessionLocal()

    try:
        # Get all resumes for user
        resumes = db.query(Resume).filter(Resume.user_id == user_id).all()

        if not resumes:
            return []

        # Score each resume
        scores = []
        for resume in resumes:
            result = score_resume(resume.id, user_id, job_title)
            if result:
                scores.append(result)

        # Sort by overall score (descending)
        scores.sort(key=lambda x: x['overall_score'], reverse=True)

        # Add rank and update database
        for i, score in enumerate(scores):
            rank = i + 1
            score['rank'] = rank

            # Check if CandidateScore exists for this resume
            candidate_score = db.query(CandidateScore).filter(
                CandidateScore.resume_id == score['resume_id']
            ).first()

            if candidate_score:
                # Update existing record
                candidate_score.rank = rank
                candidate_score.skills_match = score['skills_match']
                candidate_score.experience_match = score['experience_match']
                candidate_score.education_match = score['education_match']
                candidate_score.overall_score = score['overall_score']
            else:
                # Create new record
                new_score = CandidateScore(
                    resume_id=score['resume_id'],
                    rank=rank,
                    skills_match=score['skills_match'],
                    experience_match=score['experience_match'],
                    education_match=score['education_match'],
                    overall_score=score['overall_score']
                )
                db.add(new_score)

        # Commit all changes
        db.commit()

        return scores

    except Exception as e:
        db.rollback()
        print(f"Error ranking candidates: {e}")
        raise
    finally:
        db.close()
