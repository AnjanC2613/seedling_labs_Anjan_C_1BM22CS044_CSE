import os
import json
import logging
import requests
from fastapi import HTTPException, status
from .schemas import IssueAnalysis, IssueData

logger = logging.getLogger(__name__)


def sanitize_text(text: str, max_length: int = 10000) -> str:
    """
    Sanitize and truncate text for LLM prompts to prevent injection
    and excessive token usage.
    """
    if not text:
        return ""
    
    # Truncate to prevent excessive token usage
    text = text[:max_length]
    
    # Remove potential prompt injection patterns
    text = text.replace("</s>", "")
    text = text.replace("<|endoftext|>", "")
    text = text.replace("<|im_end|>", "")
    
    return text


def build_prompt(issue: IssueData) -> str:
    """Build a safe prompt from issue data with sanitization"""
    title = sanitize_text(issue.title, 500)
    body = sanitize_text(issue.body, 5000)
    
    # Limit to first 10 comments and sanitize each
    sanitized_comments = [
        sanitize_text(c, 2000) 
        for c in issue.comments[:10]
    ]
    comments = "\n\n---\n\n".join(sanitized_comments) if sanitized_comments else "No comments."

    return f"""You are a GitHub issue triage assistant.

Given the issue title, body, and comments, generate a JSON object with:

- "summary": One sentence summary of the user's issue or request.
- "type": bug | feature_request | documentation | question | other
- "priority_score": A score from 1 (low) to 5 (critical) with justification.
- "suggested_labels": 2–3 GitHub labels.
- "potential_impact": If bug, describe the user impact; else "N/A".

Return ONLY valid JSON, no backticks, no markdown.

Title:
{title}

Body:
{body}

Comments:
{comments}
"""


def clean_llm_response(text: str) -> str:
    """Remove markdown code blocks from LLM response"""
    text = text.strip()
    
    # Remove markdown code blocks more robustly
    if text.startswith("```"):
        lines = text.split("\n")
        
        # Remove opening ```json or ```
        if lines[0].strip().startswith("```"):
            lines = lines[1:]
        
        # Remove closing ```
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        
        text = "\n".join(lines).strip()
    
    return text


def analyze_issue_with_llm(issue: IssueData) -> IssueAnalysis:
    """
    Analyze a GitHub issue using HuggingFace LLM via the router endpoint.
    """
    token = os.getenv("HF_API_KEY")
    model = os.getenv("HF_MODEL", "mistralai/Mistral-7B-Instruct-v0.2")

    if not token:
        logger.error("HF_API_KEY not set in environment")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="LLM service is not configured. Please contact the administrator.",
        )

    prompt = build_prompt(issue)
    
    logger.info(f"Calling HuggingFace Router API with model: {model}")

    try:
        # Use the new router endpoint (correct endpoint)
        response = requests.post(
            "https://router.huggingface.co/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant that returns ONLY valid JSON responses with no additional text or markdown."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.2,
                "max_tokens": 1000,
            },
            timeout=60,
        )

        logger.info(f"HuggingFace response status: {response.status_code}")
        
        if response.status_code != 200:
            logger.error(f"HuggingFace API error: {response.status_code}")
            logger.error(f"Response body: {response.text}")
            
            # Parse error message
            try:
                error_data = response.json()
                error_msg = error_data.get("error", response.text)
            except:
                error_msg = response.text
            
            # Handle specific errors
            if response.status_code == 503:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="LLM model is loading. Please wait a moment and try again.",
                )
            elif response.status_code == 401:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Invalid HuggingFace API key.",
                )
            elif response.status_code == 400:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Bad request to LLM: {error_msg}. Try a different model.",
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Error from LLM service: {error_msg}",
                )

        response_data = response.json()
        logger.debug(f"Raw HuggingFace response: {response_data}")
        
        # Validate response structure
        if not response_data.get("choices"):
            logger.error("Invalid response: no choices returned")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Invalid response from LLM service.",
            )
        
        if not response_data["choices"][0].get("message"):
            logger.error("Invalid response: no message in choice")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Invalid response from LLM service.",
            )

        # Extract and clean response text
        text = response_data["choices"][0]["message"]["content"]
        text = clean_llm_response(text)
        
        logger.info(f"LLM response preview: {text[:150]}...")
        
        # Parse JSON
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"LLM returned invalid JSON: {e}")
            logger.error(f"Raw response: {text[:500]}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="LLM returned invalid JSON format. Try again or use a different model.",
            )
        
        # Validate using Pydantic model
        try:
            analysis = IssueAnalysis(**data)
            logger.info("Successfully created issue analysis")
            return analysis
        except Exception as e:
            logger.error(f"Failed to validate LLM response: {e}")
            logger.error(f"Data received: {data}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"LLM returned incomplete data: {str(e)}",
            )

    except requests.Timeout:
        logger.error("Request to HuggingFace timed out")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Request to LLM service timed out. Please try again.",
        )
    except requests.RequestException as e:
        logger.error(f"Network error calling HuggingFace: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Network error communicating with LLM service.",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in LLM analysis: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during analysis.",
        )