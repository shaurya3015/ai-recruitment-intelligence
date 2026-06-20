import re
from models import SessionLocal, Resume, CandidateScore

# Skill keywords database
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

EDUCATION_KEYWORDS = {
    'bachelors': 1.0,
    'masters': 1.5,
    'phd': 2.0,
    'computer science': 1.5,
    'engineering': 1.5,
    'data science': 1.5,
    'information technology': 1.3,
    'business': 0.8
}

def extract_skills(text: str) -> tuple:
    """Extract technical and soft skills from resume."""
    text_lower = text.lower()
    
    tech_skills = [s for s in TECHNICAL_SKILLS if s.lower() in text_lower]
    soft_skills = [s for s in SOFT_SKILLS if s.lower() in text_lower]
    
    score = len(tech_skills) * 0.5 + len(soft_skills) * 0.3
    score = min(score, 100)  # Cap at 100
    
    return tech_skills + soft_skills, score


def extract_experience(text: str) -> tuple:
    """Extract years of experience."""
    years_pattern = r'(\d+)\s+years?\s+of\s+experience'
    date_pattern = r'(\d{4})\s*-\s*(\d{4}|present|current)'
    
    years_matches = re.findall(years_pattern, text, re.IGNORECASE)
    date_matches = re.findall(date_pattern, text, re.IGNORECASE)
    
    years = 0
    
    if years_matches:
        years = max(int(y) for y in years_matches)
    elif date_matches:
        # Calculate years from dates
        total_years = 0
        for start, end in date_matches:
            if end.lower() in ['present', 'current']:
                total_years += 2025 - int(start)
            else:
                total_years += int(end) - int(start)
        years = total_years / len(date_matches) if date_matches else 0
    
    # Score: max 100 for 10+ years
    score = min((years / 10) * 100, 100)
    
    return years, score


def extract_education(text: str) -> tuple:
    """Extract education level."""
    text_lower = text.lower()
    
    degrees = []
    score = 0.0
    
    for keyword, points in EDUCATION_KEYWORDS.items():
        if keyword in text_lower:
            degrees.append(keyword)
            score = max(score, points)
    
    # Normalize to 0-100
    score = (score / 2.0) * 100
    
    return degrees, score


def score_resume(resume_id: int, user_id: int, job_title: str = ""):
    """Score a single resume based on skills, experience, and education."""
    db = SessionLocal()
    
    try:
        resume = db.query(Resume).filter(Resume.id == resume_id).first()
        
        if not resume:
            return None
        
        # Access resume attributes WHILE session is open
        file_name = resume.file_name
        text = resume.extracted_text or ""
        
        # Extract scores
        skills, skills_score = extract_skills(text)
        experience_years, experience_score = extract_experience(text)
        education_degrees, education_score = extract_education(text)
        
        # Calculate overall score
        overall_score = (skills_score * 0.4 + experience_score * 0.3 + education_score * 0.3)
        
        return {
            "resume_id": resume_id,
            "file_name": file_name,
            "skills": skills,
            "skills_match": round(skills_score, 2),
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