import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Load environment variables FIRST
load_dotenv()

from .schemas import AnalyzeIssueRequest, AnalyzeIssueResponse, IssueData
from .github_client import parse_github_repo_url, fetch_issue, fetch_issue_comments
from .llm_client import analyze_issue_with_llm

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Seedling Issue Analyzer",
    description="Analyze and triage GitHub issues using an LLM.",
    version="0.1.0",
)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Secure CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8501",  # Streamlit dev
        "http://localhost:3000",   # Alternative frontend
        # Add your production domains here
        # "https://yourdomain.com",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions without leaking sensitive information"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An internal error occurred. Please try again later."
        }
    )


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok", "service": "seedling-issue-analyzer"}


@app.post("/analyze", response_model=AnalyzeIssueResponse)
@limiter.limit("10/minute")  # Limit to 10 requests per minute per IP
async def analyze_issue(request: Request, payload: AnalyzeIssueRequest):
    """
    Analyze a GitHub issue using an LLM.
    
    Rate limited to 10 requests per minute per IP address.
    """
    logger.info(f"Analyzing issue #{payload.issue_number} from {payload.repo_url}")
    
    try:
        owner, repo = parse_github_repo_url(payload.repo_url)
        
        issue_json = await fetch_issue(owner, repo, payload.issue_number)
        comments = await fetch_issue_comments(owner, repo, payload.issue_number)
        
        issue = IssueData(
            title=issue_json.get("title", ""),
            body=issue_json.get("body", "") or "",
            comments=comments or [],
        )
        
        analysis = analyze_issue_with_llm(issue)
        
        logger.info(f"Successfully analyzed issue #{payload.issue_number}")
        return AnalyzeIssueResponse(issue=issue, analysis=analysis)
    
    except Exception as e:
        logger.error(f"Error analyzing issue: {e}")
        raise