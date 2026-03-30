"""
One-time setup: approve OPG token spending for LLM inference.
Run this once before first use.
"""

import os
import asyncio

def main():
    private_key = os.environ.get("OG_PRIVATE_KEY", "")
    if not private_key:
        raise SystemExit("Set OG_PRIVATE_KEY environment variable first")

    import opengradient as og

    llm = og.LLM(private_key=private_key)
    print("Approving OPG tokens for LLM inference (min_allowance=5)...")
    llm.ensure_opg_approval(min_allowance=5)
    print("Done! You can now run the accessibility checker.")


if __name__ == "__main__":
    main()
