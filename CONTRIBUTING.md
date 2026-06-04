# Contributing to MandiBhav by GramIQ

Thank you for your interest in contributing!

## Setup

```bash
git clone https://github.com/The-Harsh-Vardhan/GramIQ-MandiBhav.git
cd GramIQ-MandiBhav
pip install -r requirements.txt pytest
cp .env.example .env
# Add your GEMINI_API_KEY to .env
```

## Running Tests

```bash
python -m pytest tests/ -v
```

All 22 tests must pass before submitting a pull request.

## Running the Pipeline (Dev Mode)

```bash
python main.py --skip-translate    # English only, faster
python main.py                     # Full run with translations
```

## Code Style

- Follow the existing module structure — one responsibility per file.
- All new data models must be Pydantic `BaseModel` subclasses in `schemas.py`.
- All new configuration constants go in `config.py`.
- Test coverage is required for any new ingestion or analytics logic.

## Submitting Changes

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes with clear messages
4. Ensure `python -m pytest tests/ -v` passes
5. Open a Pull Request against `main`

## What NOT to Commit

- `.env` files (contains API keys)
- `output/` directory (generated runtime artifacts)
- `mandibhav.db` (runtime SQLite database)
- `tests/tmp/` (test temp files)
