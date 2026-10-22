# ClinicPilot AI — Technical Design

## Architecture

React (Vite) → FastAPI `/api/chat` → intent/slot extraction using Silra OpenAI-compatible Chat Completions → deterministic state/booking policy → REST booking endpoint → SQLite. React reads `/api/bookings` after successful booking. SQLAlchemy manages DB transactions.

## Deliberate deviations from suggested architecture

A single Python service hosts API and AI orchestration to reduce deployment overhead. No LangGraph dependency: a small explicit state machine provides the necessary behavior with fewer failure points. This is a custom agent architecture. The tool executor calls the REST endpoint in-process via ASGI TestClient rather than making a loopback network request; the same endpoint handles direct and agent-created bookings.

## Intent recognition and agent workflow

The LLM receives patient profile, relevant medical history, structured catalog, current bookings, pending slots, and six recent conversation turns. It returns a JSON object with `intent` (`qa`, `history`, `booking`, `cancel`), extracted booking slots, confirmation flag, and draft reply.

- **Q&A/recommendation:** generate grounded advice from catalog; no diagnoses or prescriptions.
- **History:** query the SQL booking table and deterministically format upcoming appointments; never trust generated appointment details.
- **Booking:** merge newly extracted slots with persisted conversation state; validate catalog IDs; ask for missing doctor/treatment/date/time; request explicit confirmation; then invoke `POST /api/bookings`.
- **Cancel:** clear only an unfinished booking request, not an existing appointment.

The LLM is responsible for understanding intent and extracting slots, not for executing SQL or declaring transaction success. Confirmation and persistence are server-side. Session state is stored in `conversation_state` in SQLite, so multiple turns survive backend restart.

## Retrieval / RAG design

Because the provided dataset contains only two clinics, four doctors, and five treatments, the app retrieves the complete small catalog from SQL and passes it as structured context to the LLM (full-context retrieval). This is grounded retrieval-augmented generation, not embedding-based vector search. For a production-sized corpus, use hybrid BM25/semantic retrieval for free-text clinic knowledge, and SQL for precise entity/booking data. The design avoids unnecessary vector dependencies and false-positive nearest-neighbor results for identifiers.

## Schema

The six CSV datasets are seeded into same-named SQLite tables with their CSV columns (IDs are primary keys). `patient_bookings` holds seeded and new records; `conversation_state(session_id, state_json)` stores pending slots and recent turns. SQLite transactions ensure atomic inserts. Foreign-key relationships are checked in application validation for this MVP. The demo fixes the current patient to `P001`.

## REST endpoints

- `POST /api/chat`: message, session_id, optional fixed patient_id → reply, intent, booked, booking.
- `POST /api/bookings`: doctor_id, treatment_id, booking_date, booking_time, optional patient_id and notes → new booking ID/status.
- `GET /api/bookings`: joined patient booking rows, including doctor and treatment names.
- `GET /api/health`: service readiness and API key configuration status.

## Safety, limitations and tradeoffs

This prototype does not diagnose or prescribe; urgent cases should seek emergency services. No real patient data should be sent to third-party LLMs. For this mock-data demo, allergy/history context is provided for personalization. There is no authentication, scheduling conflict logic, clinical decision support certification, or rate limiting. The model may produce malformed JSON or imperfect intent routing; production hardening would use validated structured outputs, retries, audit logs, consent, and clinical escalation. This MVP uses prompt-constrained JSON extraction rather than provider-native tool calling; the booking action is a deterministic REST tool executed by the orchestrator.

## Verification

Pytest covers CSV seeding, patient scoping, valid and invalid booking API calls, and a stubbed three-turn booking flow. Frontend build can be checked with `npm run build`. Live API calls must be tested with a valid Silra key and enabled model.
