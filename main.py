"""
OG Accessibility Checker
Verifiable WCAG accessibility analysis via OpenGradient TEE LLM.
Transaction hash on Base Sepolia as cryptographic proof of inference.
"""

import asyncio
import os
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bs4 import BeautifulSoup
from typing import Optional

import opengradient as og

app = FastAPI(
    title="OG Accessibility Checker",
    description="Verifiable WCAG 2.1 accessibility analysis via OpenGradient TEE",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_raw_key = os.environ.get("OG_PRIVATE_KEY", "").strip()
# Normalize: ensure 0x prefix
if _raw_key and not _raw_key.startswith("0x"):
    _raw_key = "0x" + _raw_key
PRIVATE_KEY = _raw_key

llm_client: Optional[og.LLM] = None


def get_llm():
    global llm_client
    if llm_client is None:
        if not PRIVATE_KEY:
            raise HTTPException(status_code=500, detail="OG_PRIVATE_KEY not set")
        llm_client = og.LLM(private_key=PRIVATE_KEY)
    return llm_client


WCAG_SYSTEM_PROMPT = """You are a WCAG 2.1 accessibility expert. Analyze HTML for accessibility issues.

For each issue found, provide:
1. WCAG criterion (e.g. 1.1.1 Non-text Content, Level A)
2. Element or pattern with the issue
3. What's wrong
4. How to fix it

Format your response as structured JSON with this shape:
{
  "summary": "Brief overall assessment",
  "score": <0-100 accessibility score>,
  "issues": [
    {
      "criterion": "1.1.1",
      "level": "A",
      "title": "Non-text Content",
      "element": "<img src='logo.png'>",
      "problem": "Missing alt attribute",
      "fix": "Add alt='Company logo' or alt='' if decorative"
    }
  ],
  "passed": ["List of things done correctly"],
  "recommendations": ["Top 3 priority fixes"]
}

Be concise. Focus on real issues, not hypothetical ones."""


class AnalyzeUrlRequest(BaseModel):
    url: str
    max_html_chars: int = 8000


class AnalyzeHtmlRequest(BaseModel):
    html: str
    url: Optional[str] = None


class AccessibilityReport(BaseModel):
    url: Optional[str]
    score: int
    summary: str
    issues_count: int
    issues: list
    passed: list
    recommendations: list
    proof: dict


async def fetch_html(url: str) -> str:
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, verify=False) as client:
        headers = {"User-Agent": "Mozilla/5.0 OG-Accessibility-Checker/1.0"}
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.text


def extract_relevant_html(html: str, max_chars: int = 8000) -> str:
    """Extract key accessibility-relevant HTML, truncate if needed."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove scripts, styles, comments to save tokens
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    # Get body or full doc
    body = soup.find("body") or soup
    cleaned = str(body)

    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars] + "\n<!-- [truncated for analysis] -->"

    return cleaned


async def run_analysis(html_content: str, url: Optional[str] = None) -> dict:
    client = get_llm()

    user_msg = f"Analyze this HTML for WCAG 2.1 accessibility issues:\n\n{html_content}"
    if url:
        user_msg = f"URL: {url}\n\n" + user_msg

    response = await client.chat(
        model=og.TEE_LLM.CLAUDE_HAIKU_4_5,
        messages=[
            {"role": "system", "content": WCAG_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        max_tokens=2000,
    )

    return response


@app.post("/analyze/url", response_model=AccessibilityReport)
async def analyze_url(request: AnalyzeUrlRequest):
    """Fetch a URL and analyze its HTML for WCAG 2.1 accessibility issues."""
    try:
        raw_html = await fetch_html(request.url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {e}")

    html_content = extract_relevant_html(raw_html, request.max_html_chars)
    return await process_analysis(html_content, request.url)


@app.post("/analyze/html", response_model=AccessibilityReport)
async def analyze_html(request: AnalyzeHtmlRequest):
    """Analyze provided HTML for WCAG 2.1 accessibility issues."""
    html_content = extract_relevant_html(request.html)
    return await process_analysis(html_content, request.url)


async def process_analysis(html_content: str, url: Optional[str]) -> AccessibilityReport:
    try:
        response = await run_analysis(html_content, url)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OpenGradient inference error: {e}")

    # Parse LLM JSON output
    import json
    import re

    raw_text = response.chat_output.get("content", "") if response.chat_output else ""

    # Extract JSON block from response
    json_match = re.search(r"\{[\s\S]*\}", raw_text)
    if not json_match:
        raise HTTPException(status_code=502, detail="Invalid response format from LLM")

    try:
        analysis = json.loads(json_match.group())
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=502, detail=f"JSON parse error: {e}")

    return AccessibilityReport(
        url=url,
        score=analysis.get("score", 0),
        summary=analysis.get("summary", ""),
        issues_count=len(analysis.get("issues", [])),
        issues=analysis.get("issues", []),
        passed=analysis.get("passed", []),
        recommendations=analysis.get("recommendations", []),
        proof={
            "transaction_hash": response.transaction_hash,
            "payment_hash": response.payment_hash,
            "tee_signature": response.tee_signature,
            "tee_timestamp": response.tee_timestamp,
            "tee_id": response.tee_id,
            "model": str(og.TEE_LLM.CLAUDE_HAIKU_4_5),
            "network": "Base Sepolia",
        },
    )


@app.on_event("startup")
async def startup_event():
    """Ensure OPG Permit2 allowance matches current balance on server start."""
    if not PRIVATE_KEY:
        return
    try:
        from web3 import Web3
        from eth_account import Account
        from opengradient.client.opg_token import BASE_SEPOLIA_RPC, BASE_OPG_ADDRESS
        import logging

        w3 = Web3(Web3.HTTPProvider(BASE_SEPOLIA_RPC))
        addr = Account.from_key(PRIVATE_KEY).address
        ABI = [{"inputs":[{"name":"account","type":"address"}],"name":"balanceOf",
                "outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"}]
        c = w3.eth.contract(address=Web3.to_checksum_address(BASE_OPG_ADDRESS), abi=ABI)
        bal = c.functions.balanceOf(addr).call()
        bal_float = bal / 1e18

        if bal_float >= 0.1:
            client = get_llm()
            client.ensure_opg_approval(min_allowance=bal_float - 0.001, approve_amount=bal_float)
            logging.info(f"OPG Permit2 approval set to {bal_float} OPG")
        else:
            logging.warning(f"OPG balance too low: {bal_float} OPG (need >= 0.1)")
    except Exception as e:
        import logging
        logging.warning(f"OPG approval startup check failed: {e}")


@app.get("/debug/env")
async def debug_env():
    """Temporary: check env variable state."""
    raw = os.environ.get("OG_PRIVATE_KEY", "NOT_SET")
    return {
        "raw_len": len(raw),
        "has_0x": raw.startswith("0x"),
        "first_4": raw[:4] if len(raw) >= 4 else raw,
        "PRIVATE_KEY_len": len(PRIVATE_KEY),
    }


@app.get("/health")
async def health():
    return {"status": "ok", "sdk_version": og.__version__ if hasattr(og, "__version__") else "unknown"}


@app.get("/")
async def root():
    return {
        "name": "OG Accessibility Checker",
        "description": "Verifiable WCAG 2.1 accessibility analysis via OpenGradient TEE",
        "endpoints": {
            "POST /analyze/url": "Analyze accessibility of a public URL",
            "POST /analyze/html": "Analyze provided HTML string",
            "GET /health": "Service health check",
        },
        "docs": "/docs",
    }
