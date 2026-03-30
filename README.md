# OG Accessibility Checker

Verifiable WCAG 2.1 accessibility analysis powered by [OpenGradient](https://opengradient.ai) TEE LLM inference.

Every analysis produces an on-chain transaction hash on Base Sepolia as cryptographic proof that Claude Haiku ran inside a Trusted Execution Environment (TEE) — tamper-proof and auditable.

## Features

- Analyze any public URL or raw HTML
- WCAG 2.1 criteria mapping (Level A, AA, AAA)
- Accessibility score 0-100
- On-chain proof: `transaction_hash` on Base Sepolia
- TEE signature for cryptographic verification
- OpenAPI docs at `/docs`

## Quick Start

```bash
# 1. Clone
git clone https://github.com/web3blind/og-accessibility-checker
cd og-accessibility-checker

# 2. Install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Get OPG tokens (testnet faucet)
# https://faucet.opengradient.ai
# Approve OPG spending (one-time):
python3 setup_approval.py

# 4. Configure
cp .env.example .env
# Edit .env: set OG_PRIVATE_KEY=0x...

# 5. Run
uvicorn main:app --host 0.0.0.0 --port 8000
```

## API Usage

### Analyze a URL

```bash
curl -X POST http://localhost:8000/analyze/url \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
```

### Analyze HTML directly

```bash
curl -X POST http://localhost:8000/analyze/html \
  -H "Content-Type: application/json" \
  -d '{"html": "<html><body><img src=logo.png></body></html>"}'
```

### Response example

```json
{
  "url": "https://example.com",
  "score": 72,
  "summary": "Page has several accessibility issues, mainly missing alt text and low contrast.",
  "issues_count": 3,
  "issues": [
    {
      "criterion": "1.1.1",
      "level": "A",
      "title": "Non-text Content",
      "element": "<img src='hero.jpg'>",
      "problem": "Missing alt attribute",
      "fix": "Add alt='Description of image'"
    }
  ],
  "passed": ["Page has lang attribute", "Headings are in order"],
  "recommendations": ["Add alt text to all images", "Improve color contrast", "Add ARIA labels to form inputs"],
  "proof": {
    "transaction_hash": "0xabc123...",
    "tee_signature": "...",
    "tee_timestamp": "2025-01-01T00:00:00Z",
    "model": "anthropic/claude-haiku-4-5",
    "network": "Base Sepolia"
  }
}
```

## Architecture

```
User → FastAPI → fetch HTML → extract relevant tags
             → OpenGradient TEE (Claude Haiku)
             → WCAG JSON analysis
             → response + on-chain tx_hash
```

## Proof of Verifiable Inference

The `proof.transaction_hash` in every response is a real Base Sepolia transaction.  
Verify at: `https://sepolia.basescan.org/tx/{transaction_hash}`

The `proof.tee_signature` is an RSA-PSS signature produced inside the TEE enclave over the response content.

## Built With

- [OpenGradient Python SDK](https://docs.opengradient.ai/developers/sdk/)
- FastAPI + uvicorn
- BeautifulSoup4
- Model: `anthropic/claude-haiku-4-5` (TEE-verified)
- Network: Base Sepolia (x402 payment protocol)

## License

MIT
