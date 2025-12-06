# Seedling Issue Analyzer 🌱

A lightweight web app to triage GitHub issues using an LLM.

## Features
- Fetches GitHub issues via API
- Analyzes with HuggingFace LLMs
- Returns structured JSON summaries
- Rate limiting and security features

## Setup

1. Clone the repository
2. Create a virtual environment:
```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
   pip install -r requirements.txt
```

4. Create `.env` file (copy from `.env.example`):
```bash
   cp .env.example .env
```

5. Add your API keys to `.env`:
   - Get HuggingFace API key from: https://huggingface.co/settings/tokens
   - Get GitHub token from: https://github.com/settings/tokens

6. Run the backend:
```bash
   python -m uvicorn backend.main:app --reload
```

7. Run the frontend (in another terminal):
```bash
   streamlit run app.py
```

8. Visit http://localhost:8501

## Security Features
- ✅ Rate limiting (10 requests/min)
- ✅ Input validation and sanitization
- ✅ Secure CORS configuration
- ✅ Comprehensive error handling
- ✅ No API keys in code

## Configuration

Edit `.env` to customize:
- `HF_MODEL`: Choose from supported HuggingFace models
- `GITHUB_TOKEN`: Optional, increases rate limits

## License
MIT