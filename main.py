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


WCAG_SYSTEM_PROMPT = """You are a WCAG 2.1 Level AA accessibility expert auditing HTML source code.

Analyze the provided HTML and check ALL of the following categories. Only report issues you can actually detect from the static HTML — do not invent issues.

PERCEIVABLE:
- Images: missing or non-descriptive alt text (WCAG 1.1.1 Level A)
- Decorative images: should have alt="" and role="presentation" (WCAG 1.1.1)
- Color as sole information conveyor — check error/required field markers (WCAG 1.4.1 Level A)
- lang attribute on <html> element (WCAG 3.1.1 Level A)
- Orientation lock via CSS (WCAG 1.3.4 Level AA)
- autocomplete attributes on personal data fields: name, email, tel, address (WCAG 1.3.5 Level AA)

OPERABLE:
- Skip navigation link "Skip to main content" (WCAG 2.4.1 Level A)
- Meaningful <title> tag — not empty, not generic (WCAG 2.4.2 Level A)
- Keyboard traps — interactive elements without keyboard access (WCAG 2.1.1/2.1.2 Level A)
- Focus indicators — CSS outline:none/outline:0 without replacement (WCAG 2.4.7 Level AA)
- Descriptive link text — not "click here", "read more", "link" (WCAG 2.4.4 Level A)
- Drag-and-drop without pointer alternative (WCAG 2.5.7 Level AA)
- Touch/click targets smaller than 24x24px (WCAG 2.5.8 Level AA)

UNDERSTANDABLE:
- Form inputs without associated <label> (WCAG 1.3.1 / 3.3.2 Level A)
- Error messages that are generic or unclear (WCAG 3.3.1 / 3.3.3 Level A/AA)
- Instructions using only sensory characteristics (color, shape, location) (WCAG 1.3.3 Level A)
- Inconsistent navigation or labeling (WCAG 3.2.3 / 3.2.4 Level AA)

ROBUST:
- Buttons/links without accessible names (WCAG 4.1.2 Level A)
- aria-hidden="true" on interactive elements (WCAG 4.1.2 Level A)
- Incorrect or missing ARIA roles/states (WCAG 4.1.2 Level A)
- Status messages without role="status" or aria-live (WCAG 4.1.3 Level AA)
- iframes without title attribute (WCAG 4.1.2 Level A)
- Duplicate id attributes (WCAG 4.1.1 Level A)

STRUCTURE:
- Heading hierarchy: one <h1>, no skipped levels (h1→h2→h3)
- Landmarks: <main>, <nav>, <header>, <footer> present
- Tables: <th> with scope, <caption> if needed
- Lists: <ul>/<ol>/<dl> used semantically

For issues that CANNOT be verified from static HTML (contrast ratios, focus order, time limits, dynamic content), mark them as [MANUAL CHECK REQUIRED] if you see risk signals (e.g. suspicious color values in inline styles).

Respond with ONLY valid JSON in this exact shape:
{
  "summary": "1-2 sentence overall assessment",
  "score": <integer 0-100>,
  "issues": [
    {
      "criterion": "1.1.1",
      "level": "A",
      "title": "Non-text Content",
      "severity": "critical|warning|info",
      "element": "<img src='logo.png'>",
      "problem": "Missing alt attribute — screen readers will read the filename",
      "fix": "Add alt='Description' or alt='' with role='presentation' if decorative"
    }
  ],
  "passed": ["Specific things verified as correct"],
  "manual_checks": ["Things that require browser/screen reader testing"],
  "recommendations": ["Top 3 priority fixes in order of importance"]
}

Score formula: start at 100, deduct 10 per critical issue, 5 per warning, 1 per info.
Be concise. Only report what you can actually see in the HTML."""


class AnalyzeUrlRequest(BaseModel):
    url: str
    max_html_chars: int = 8000
    use_playwright: bool = True  # Render JS via headless Chromium before analysis; falls back to httpx if unavailable


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
    manual_checks: list
    recommendations: list
    proof: dict
    rendered: bool = False  # True if HTML was fetched via Playwright (JS rendered)
    fetch_mode: str = "httpx"  # "playwright" or "httpx" — indicates completeness of HTML analysis


async def fetch_html(url: str) -> str:
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, verify=False) as client:
        headers = {"User-Agent": "Mozilla/5.0 OG-Accessibility-Checker/1.0"}
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.text


async def fetch_html_rendered(url: str, timeout: int = 45) -> str:
    """Fetch fully rendered HTML via headless Chromium (Playwright).
    Requires playwright + chromium installed locally.
    Falls back to plain httpx fetch if playwright is unavailable.
    """
    import asyncio
    import subprocess
    import sys

    # Try to find playwright-capable python — auditor venv or current interpreter
    candidates = [
        os.path.expanduser("~/.hermes/agents/accessibility-auditor/venv/bin/python3"),
        sys.executable,
    ]
    fetch_script = os.path.expanduser(
        "~/.hermes/agents/accessibility-auditor/fetch_page.py"
    )

    python_bin = None
    if os.path.exists(fetch_script):
        for candidate in candidates:
            if os.path.exists(candidate):
                python_bin = candidate
                break

    if not python_bin:
        # Playwright not available — fall back to httpx
        return await fetch_html(url)

    loop = asyncio.get_event_loop()
    try:
        proc = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    [python_bin, fetch_script, url, str(timeout)],
                    capture_output=True,
                    text=True,
                    timeout=timeout + 20,
                ),
            ),
            timeout=timeout + 25,
        )
        if proc.returncode == 0 and proc.stdout:
            return proc.stdout
        # Playwright failed — fall back to httpx
        return await fetch_html(url)
    except Exception:
        return await fetch_html(url)


def extract_relevant_html(html: str, max_chars: int = 8000) -> str:
    """Extract key accessibility-relevant HTML, truncate if needed.

    Preserves <html lang=...> and <head> metadata (title, meta) since they
    contain critical WCAG signals (3.1.1 lang, 2.4.2 title, etc.).
    Removes scripts/styles/SVGs to save tokens.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Remove noise
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    # Build compact head — only accessibility-relevant tags
    head_parts = []
    html_tag = soup.find("html")
    lang = html_tag.get("lang", "") if html_tag else ""
    head_parts.append(f'<html lang="{lang}">' if lang else "<html>")

    head = soup.find("head")
    if head:
        title = head.find("title")
        if title:
            head_parts.append(str(title))
        for meta in head.find_all("meta"):
            name = meta.get("name", "") or meta.get("property", "")
            if name in ("description", "robots", "viewport"):
                head_parts.append(str(meta))
    head_parts.append("</head>")

    # Body content
    body = soup.find("body") or soup
    body_str = str(body)

    # Budget: head always fits, trim body to remaining budget
    head_str = "\n".join(head_parts)
    body_budget = max_chars - len(head_str) - 50
    if len(body_str) > body_budget:
        body_str = body_str[:body_budget] + "\n<!-- [truncated for analysis] -->"

    return head_str + "\n" + body_str


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
    """Fetch a URL and analyze its HTML for WCAG 2.1 accessibility issues.

    Set use_playwright=true to render JavaScript before analysis (local only).
    Falls back to plain HTTP fetch if Playwright/Chromium is unavailable.
    """
    try:
        if request.use_playwright:
            raw_html = await fetch_html_rendered(request.url)
        else:
            raw_html = await fetch_html(request.url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {e}")

    html_content = extract_relevant_html(raw_html, request.max_html_chars)
    return await process_analysis(html_content, request.url, rendered=request.use_playwright)


@app.post("/analyze/html", response_model=AccessibilityReport)
async def analyze_html(request: AnalyzeHtmlRequest):
    """Analyze provided HTML for WCAG 2.1 accessibility issues."""
    html_content = extract_relevant_html(request.html)
    return await process_analysis(html_content, request.url)


async def process_analysis(html_content: str, url: Optional[str], rendered: bool = False) -> AccessibilityReport:
    try:
        response = await run_analysis(html_content, url)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OpenGradient inference error: {e}")

    # Parse LLM JSON output
    import json
    import re

    raw_text = response.chat_output.get("content", "") if response.chat_output else ""

    # Extract JSON block from response — try full match first, then repair
    json_match = re.search(r"\{[\s\S]*\}", raw_text)
    if not json_match:
        raise HTTPException(status_code=502, detail="Invalid response format from LLM")

    json_str = json_match.group()
    analysis = None

    # Attempt 1: direct parse
    try:
        analysis = json.loads(json_str)
    except json.JSONDecodeError:
        pass

    # Attempt 2: find last complete top-level closing brace
    if analysis is None:
        depth = 0
        last_valid_end = 0
        for i, ch in enumerate(json_str):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    last_valid_end = i + 1
        if last_valid_end:
            try:
                analysis = json.loads(json_str[:last_valid_end])
            except json.JSONDecodeError:
                pass

    if analysis is None:
        raise HTTPException(status_code=502, detail="Could not parse LLM JSON response")

    mode = "playwright" if rendered else "httpx"
    return AccessibilityReport(
        url=url,
        score=analysis.get("score", 0),
        summary=analysis.get("summary", ""),
        issues_count=len(analysis.get("issues", [])),
        issues=analysis.get("issues", []),
        passed=analysis.get("passed", []),
        manual_checks=analysis.get("manual_checks", []),
        recommendations=analysis.get("recommendations", []),
        rendered=rendered,
        fetch_mode=mode,
        proof={
            "transaction_hash": response.transaction_hash,
            "payment_hash": response.payment_hash,
            "tee_signature": response.tee_signature,
            "tee_timestamp": response.tee_timestamp,
            "tee_id": response.tee_id,
            "model": str(og.TEE_LLM.CLAUDE_HAIKU_4_5),
            "network": "Base Sepolia",
            "fetch_mode": mode,
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
