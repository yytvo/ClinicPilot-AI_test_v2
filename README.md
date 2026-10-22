# ClinicPilot AI

A local-first medical clinic assistant demo: grounded clinic Q&A, treatment/doctor recommendations, patient booking lookup, and confirmed appointment creation via a REST tool. Uses six provided CSV datasets.

## Prerequisites

- macOS (or Windows/Linux), Python 3.10+, Node.js 18+
- Silra API key and an enabled chat-completions model
- No GPU, Docker, PostgreSQL, or embedding model required

## Start

From the repository root:

```bash
python3 configure.py
# Enter your newly generated Silra key (hidden input) and an enabled model ID.
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn app.main:app --app-dir backend --reload
```

In a **second terminal**:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Backend API documentation: http://localhost:8000/docs.

The database is created and seeded automatically on first start as `clinicpilot.db`. It persists subsequent bookings across restarts. To reset, stop the server and delete `clinicpilot.db` (this also deletes any new bookings).

## Where is .env.example?

It is included in the ZIP, but macOS Finder hides dotfiles. Press **Command + Shift + .** in Finder to show hidden files. You do not need to locate it: `python3 configure.py` creates `.env` automatically. Never commit `.env` to GitHub.

## Environment

`LLM_API_KEY`: Silra bearer token (required for AI chat)

`LLM_BASE_URL`: defaults to `https://api.silra.cn/v1`

`LLM_MODEL`: model enabled on your Silra account; example `deepseek-chat-fast` (availability must be confirmed in your account)

The provider documents `/v1/chat/completions`. The user-supplied `/v1/responses` endpoint is not assumed to be compatible with this implementation.

## Test

```bash
source .venv/bin/activate
PYTHONPATH=backend pytest backend/tests -q
cd frontend && npm run build
```

API tests stub the LLM, so no key is needed. Live AI chat requires the API key.

## Live demo script

1. Ask: "What doctors and treatments do you have?"
2. Ask: "I have knee pain. Who should I see?" (recommendation is not diagnosis)
3. Ask: "When is my next appointment?"
4. Ask: "Book a general checkup with Dr Sarah Jenkins".
5. Supply a future date and time in another message.
6. Say "confirm". Watch the booking appear in the right panel.
7. Refresh the page and the booking list to show persistence.

## Security and limitations

This is **mock-data-only**, with a fixed P001 identity and no authentication. Never deploy with real patient records without authentication, authorization, consent, logging controls, and regulatory review. No schedule conflicts are checked, per assignment. The app does not diagnose, prescribe, or automatically modify existing bookings. No key is stored in the browser. Do not commit `.env` or `clinicpilot.db`.
