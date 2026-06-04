# Security Policy

## Supported Versions

This is a Proof-of-Concept (PoC) project built for the GramIQ assignment.
Only the `main` branch is actively maintained.

## Reporting a Vulnerability

If you discover a security vulnerability, please do **not** open a public GitHub issue.

Instead, contact the maintainer directly via the email on the GitHub profile.

## API Key Safety

This project requires API keys (`GEMINI_API_KEY`, `OGD_API_KEY`).

**IMPORTANT:**
- **Never commit your `.env` file.** It is excluded by `.gitignore`.
- Always use `.env.example` as the template — it contains no real credentials.
- If you accidentally expose an API key, revoke it immediately at:
  - Gemini: https://aistudio.google.com/app/apikey
  - OGD (data.gov.in): https://data.gov.in/user/me/api-key
- The pipeline runs completely in `dev` mode without any API keys.
  Only `GEMINI_API_KEY` is required for article generation.

## Running Safely

```bash
# Safe: copy the example, fill in only your own keys
cp .env.example .env

# Never do this:
git add .env   # ← .gitignore prevents this, but always double-check
```
