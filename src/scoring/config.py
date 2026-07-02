"""
config.py — All constants and scoring configuration for the CandidateRank-AI system.
No functions — pure constants only.
"""

# ---------------------------------------------------------------------------
# Score weights (sum = 0.75; behavioral is a MULTIPLIER, not additive)
# ---------------------------------------------------------------------------
WEIGHTS = {
    "career":     0.30,
    "skills":     0.20,
    "experience": 0.15,
    "location":   0.10,
}

# ---------------------------------------------------------------------------
# Title classification
# ---------------------------------------------------------------------------
HIGH_RELEVANCE_TITLES = [
    "ml engineer",
    "machine learning engineer",
    "data scientist",
    "ai engineer",
    "artificial intelligence engineer",
    "software engineer",
    "backend engineer",
    "applied scientist",
    "research engineer",
    "nlp engineer",
    "senior engineer",
    "staff engineer",
    "principal engineer",
    "ml research engineer",
    "recommendation systems engineer",
    "search engineer",
    "ranking engineer",
]

LOW_RELEVANCE_TITLES = [
    "marketing manager",
    "hr manager",
    "human resources manager",
    "accountant",
    "graphic designer",
    "sales manager",
    "content writer",
    "social media manager",
    "recruiter",
    "business development manager",
    "administrative assistant",
    "customer support",
    "product marketing",
]

# ---------------------------------------------------------------------------
# Career / description keyword signals (technical depth indicators)
# ---------------------------------------------------------------------------
CAREER_KEYWORDS = [
    "embedding",
    "embeddings",
    "ranking",
    "retrieval",
    "vector db",
    "vector database",
    "recommendation",
    "nlp",
    "search",
    "deployed",
    "production",
    "pipeline",
    "model",
    "fine-tuning",
    "fine tuning",
    "transformer",
    "bert",
    "llm",
    "rag",
    "reranking",
    "re-ranking",
    "faiss",
    "pinecone",
    "elasticsearch",
    "learning to rank",
    "learning-to-rank",
    "ann",
    "approximate nearest neighbor",
    "semantic search",
]

# ---------------------------------------------------------------------------
# Consulting firm detection (consulting-only career = strong negative signal)
# ---------------------------------------------------------------------------
CONSULTING_FIRMS = {
    "tcs",
    "tata consultancy services",
    "infosys",
    "wipro",
    "accenture",
    "cognizant",
    "capgemini",
    "hcl",
    "hcl technologies",
    "tech mahindra",
    "mphasis",
    "hexaware",
    "mindtree",
    "l&t infotech",
    "ltimindtree",
}

# ---------------------------------------------------------------------------
# Skills taxonomy
# ---------------------------------------------------------------------------
MUST_HAVE_SKILLS = [
    "embeddings",
    "vector db",
    "python",
    "nlp",
    "ranking",
    "retrieval",
    "search",
    "ndcg",
    "mrr",
    "map",
    "machine learning",
    "deep learning",
]

NICE_TO_HAVE_SKILLS = [
    "llm fine-tuning",
    "lora",
    "learning-to-rank",
    "distributed systems",
    "faiss",
    "elasticsearch",
    "rag",
    "transformers",
    "pytorch",
    "tensorflow",
    "kubernetes",
    "docker",
]

# ---------------------------------------------------------------------------
# Experience Gaussian Curve Parameters
# ---------------------------------------------------------------------------
# Used to calculate experience_band_score using e^(-(years - target)^2 / (2 * std_dev^2))
EXPERIENCE_TARGET_YEARS = 7.0
EXPERIENCE_STD_DEV = 2.5

# ---------------------------------------------------------------------------
# Geography
# ---------------------------------------------------------------------------
INDIA_HUBS = {
    "noida",
    "pune",
    "hyderabad",
    "mumbai",
    "delhi ncr",
    "delhi",
    "gurgaon",
    "gurugram",
    "bangalore",
    "bengaluru",
    "chennai",
    "kolkata",
    "ahmedabad",
}

# ---------------------------------------------------------------------------
# Honeypot detection thresholds
# ---------------------------------------------------------------------------
HONEYPOT_MIN_SIGNALS        = 2          # require 2+ corroborating checks for hard exclusion
HONEYPOT_HARD_SCORE         = float("-inf")

# Duration mismatch tolerance (months)
HONEYPOT_DURATION_TOLERANCE = 6

# How many months of over-claimed experience triggers inflation check
HONEYPOT_INFLATION_THRESHOLD = 36

# Expert skill with less than this many months usage → suspicious
HONEYPOT_EXPERT_MIN_MONTHS  = 3

# ---------------------------------------------------------------------------
# Behavioral multiplier
# ---------------------------------------------------------------------------
BEHAVIORAL_MULTIPLIER_RANGE = (0.2, 1.3)

# ---------------------------------------------------------------------------
# Default for missing / null fields — never penalize absence of data
# ---------------------------------------------------------------------------
NEUTRAL_SCORE = 0.6

# ---------------------------------------------------------------------------
# Job-hopper detection
# ---------------------------------------------------------------------------
JOB_HOPPER_AVG_TENURE_MONTHS = 18  # 1.5 years per original spec
JOB_HOPPER_MIN_JOBS          = 4
JOB_HOPPER_PENALTY_FACTOR    = 0.6

# ---------------------------------------------------------------------------
# Consulting firm career penalty
# ---------------------------------------------------------------------------
CONSULTING_PENALTY_FACTOR = 0.5

# ---------------------------------------------------------------------------
# Product company career bonus (Fix 3)
# ---------------------------------------------------------------------------
PRODUCT_COMPANY_BONUS = 0.15

# ---------------------------------------------------------------------------
# Behavioral signal weights (Fix 1)
# Must sum to 1.0
# ---------------------------------------------------------------------------
BEHAVIORAL_SIGNAL_WEIGHTS = {
    "recruiter_response_rate":    0.30,
    "recency":                    0.25,
    "interview_completion_rate":  0.15,
    "github_activity":            0.15,
    "profile_completeness":       0.10,
    "trust":                      0.05,
}
