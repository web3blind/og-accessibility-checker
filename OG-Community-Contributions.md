# OG Community Contributions — Denis Skripnik (web3blind)

**Discord Username:** web3blind  
**X Profile:** https://x.com/Denis_skripnik

---

## Community Builds

| # | Project Name | Date | Website URL | GitHub URL |
|---|---|---|---|---|
| 1 | OG Accessibility Checker | 2026-03-31 | https://web-production-9e6cc.up.railway.app/docs | https://github.com/web3blind/og-accessibility-checker |

---

## Project Description

WCAG 2.1 accessibility auditor built on **OpenGradient TEE LLM**.

Analyzes any website for accessibility issues with **cryptographic proof** that inference happened inside a Trusted Execution Environment.

**What it does:**
- Fetches pages via Playwright (full JS render — not just static HTML)
- Sends structured HTML to Claude Haiku 4.5 via OpenGradient TEE
- Returns scored WCAG 2.1 audit: issues, passed checks, recommendations
- Every result includes tee_signature, tee_id, tee_timestamp as verifiable proof

**Stack:** Python, FastAPI, OpenGradient SDK, Playwright, Railway, Base Sepolia

---

## Live Demo — Audit of opengradient.ai

Ran the auditor on OpenGradient's own website as a demonstration.

**Score: 78/100** | fetch_mode: playwright | 5 issues found

### Issues Found
- CRITICAL 2.4.1 — No skip navigation link
- CRITICAL 4.1.2 — Nav dropdown buttons: icon spans missing aria-hidden="true"
- WARNING 4.1.2 — Mobile menu button: icon span not marked as decorative
- INFO 4.1.3 — Loading div uses both aria-live and sr-only span redundantly
- INFO 1.3.5 — Verify autocomplete on hidden form fields

### Passed (8 checks)
- lang="en" on html element (WCAG 3.1.1)
- Meaningful title tag (WCAG 2.4.2)
- Semantic landmarks: header, nav, section (WCAG 1.3.1)
- Focus indicators: focus-visible:ring-2 (WCAG 2.4.7)
- Image alt text present (WCAG 1.1.1)
- Descriptive link text (WCAG 2.4.4)
- aria-live on status messages (WCAG 4.1.3)
- Viewport meta configured (WCAG 1.3.4)

---

## TEE Cryptographic Proof

tee_id:        93983050337f32a70e69422bc479898604aa959faa4f16b58700605ccf3dd54c
tee_timestamp: 1774939403 (2026-03-31)
model:         TEE_LLM.CLAUDE_HAIKU_4_5
network:       Base Sepolia
tee_signature: pYNrdviGaHBd3JACeVtJ/mEALTM53XHW3GWZlwrn4kESmwpWAq3SyDevAezeLL+3lxIbo/tMmjfMlLbNHEnk1IaksSisAl/y0yXG1klAEHTL25NOdSqpolr5U91+s4drNdaxfAq4C1jg2AKuau0e8Wk+656T3SOJaVVGeDYSXgjVtdngrA/6q9T0ah5xQE03hMjdV1QwO/UHIkLnwT+ffT1mW6juD03mJAUR37Klyz3pMDfcE8sktgD50ZcXnLq4VQsBoTINWjSWvNbjNnwnhyC7dJwqla6i1+WO1AHPAeebolk48xXyJJa60Inf+tfzSmTRFyugeKT8TSLBToUXvA==

---

## Community Support & Impact

- Shared in OpenGradient Discord
- Published on X: https://x.com/Denis_skripnik
- First project to run a verifiable WCAG audit on opengradient.ai using their own TEE infrastructure
