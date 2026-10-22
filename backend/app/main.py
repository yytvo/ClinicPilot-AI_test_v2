"""ClinicPilot: grounded clinic assistant with explicit, auditable booking tools."""
import csv
import json
import os
import re
import sqlite3
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / '.env')
DB = os.getenv('DATABASE_URL', f'sqlite:///{ROOT / "clinicpilot.db"}')
engine = create_engine(DB, connect_args={'check_same_thread': False} if DB.startswith('sqlite') else {})
app = FastAPI(title='ClinicPilot AI')
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'], allow_methods=['*'], allow_headers=['*'])
TABLES = ['clinics', 'doctors', 'treatments', 'patients', 'patient_bookings', 'patient_treatment_history']
# Fixed schema for mock CSV data; no user-provided table/column names are interpolated.

def seed():
    with engine.begin() as conn:
        for table in TABLES:
            with (ROOT / 'mock-data' / f'{table}.csv').open(newline='', encoding='utf-8-sig') as f:
                rows = list(csv.DictReader(f))
            columns = list(rows[0])
            defs = ', '.join(f'"{c}" TEXT' + (' PRIMARY KEY' if c == columns[0] else '') for c in columns)
            conn.execute(text(f'CREATE TABLE IF NOT EXISTS "{table}" ({defs})'))
            for row in rows:
                names = ', '.join(f'"{c}"' for c in columns)
                values = ', '.join(f':{c}' for c in columns)
                conn.execute(text(f'INSERT OR IGNORE INTO "{table}" ({names}) VALUES ({values})'), row)
        conn.execute(text('CREATE TABLE IF NOT EXISTS conversation_state (session_id TEXT PRIMARY KEY, state_json TEXT NOT NULL)'))

seed()

def rows(sql, **params):
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(text(sql), params).mappings()]

class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=3000)
    session_id: str = Field(default='demo', max_length=100)
    patient_id: Literal['P001'] = 'P001'

class BookingIn(BaseModel):
    patient_id: Literal['P001'] = 'P001'
    doctor_id: str
    treatment_id: str
    booking_date: date
    booking_time: str
    notes: str = ''

class ChatOut(BaseModel):
    reply: str
    intent: str
    booked: bool = False
    booking: dict | None = None

@app.get('/api/health')
def health():
    return {'ok': True, 'llm_configured': bool(os.getenv('LLM_API_KEY'))}

@app.get('/api/bookings')
def bookings(patient_id: Literal['P001'] = 'P001'):
    return rows('''SELECT b.*, d.full_name AS doctor_name, t.treatment_name
        FROM patient_bookings b JOIN doctors d ON b.doctor_id=d.doctor_id
        JOIN treatments t ON b.treatment_id=t.treatment_id
        WHERE b.patient_id=:pid ORDER BY b.booking_date, b.booking_time''', pid=patient_id)

@app.post('/api/bookings', status_code=201)
def create_booking(b: BookingIn):
    if b.booking_date < date.today():
        raise HTTPException(422, 'Cannot book a past date')
    try:
        datetime.strptime(b.booking_time, '%H:%M')
    except ValueError:
        raise HTTPException(422, 'Time must be HH:MM (24-hour)')
    if not rows('SELECT doctor_id FROM doctors WHERE doctor_id=:id', id=b.doctor_id):
        raise HTTPException(422, 'Unknown doctor')
    if not rows('SELECT treatment_id FROM treatments WHERE treatment_id=:id', id=b.treatment_id):
        raise HTTPException(422, 'Unknown treatment')
    bid = 'B' + uuid.uuid4().hex[:10].upper()
    with engine.begin() as conn:
        conn.execute(text('''INSERT INTO patient_bookings
        (booking_id,patient_id,doctor_id,treatment_id,booking_date,booking_time,status,notes)
        VALUES (:id,:pid,:doc,:tr,:day,:tm,'Confirmed',:notes)'''),
        {'id': bid, 'pid': b.patient_id, 'doc': b.doctor_id, 'tr': b.treatment_id,
         'day': b.booking_date.isoformat(), 'tm': b.booking_time + ':00', 'notes': b.notes})
    return {'booking_id': bid, 'status': 'Confirmed'}


def llm_json(system, user):
    """Call OpenAI-compatible Chat Completions. No API key is ever returned to the client."""
    key = os.getenv('LLM_API_KEY')
    if not key:
        raise HTTPException(503, 'LLM_API_KEY missing. Set it in .env to enable AI chat.')
    url = os.getenv('LLM_BASE_URL', 'https://api.silra.cn/v1').rstrip('/') + '/chat/completions'
    try:
        with httpx.Client(timeout=40) as client:
            response = client.post(url, headers={'Authorization': f'Bearer {key}'}, json={
                'model': os.getenv('LLM_MODEL', 'deepseek-chat-fast'),
                'messages': [{'role':'system','content':system},{'role':'user','content':user}],
                'temperature': 0, 'stream': False})
            response.raise_for_status()
            content = response.json()['choices'][0]['message']['content']
            match = re.search(r'\{.*\}', content, flags=re.S)
            return json.loads(match.group(0)) if match else {}
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as e:
        raise HTTPException(502, f'LLM provider error: {str(e)[:180]}')


def state_get(sid):
    data = rows('SELECT state_json FROM conversation_state WHERE session_id=:sid', sid=sid)
    return json.loads(data[0]['state_json']) if data else {'pending': {}, 'history': []}

def state_put(sid, state):
    with engine.begin() as conn:
        conn.execute(text('INSERT OR REPLACE INTO conversation_state (session_id,state_json) VALUES (:sid,:val)'),
                     {'sid': sid, 'val': json.dumps(state)})


def catalog():
    return {table: rows(f'SELECT * FROM {table}') for table in ['clinics','doctors','treatments']}

SYSTEM = '''You are ClinicPilot, a clinic information and appointment assistant, not a doctor.
Return ONLY a JSON object with keys: intent (qa|history|booking|cancel),
reply (brief helpful English), doctor_id, treatment_id, booking_date, booking_time, confirm (boolean).
Use null for missing values. For booking_date use YYYY-MM-DD and booking_time HH:MM (24h).
Resolve relative dates against today's date. Select IDs only from the supplied catalog.
For symptoms recommend an appropriate service/doctor without diagnosing or prescribing.
Never invent clinical facts, appointments, or availability. Respect listed allergies.
If urgent or life-threatening symptoms, recommend emergency services.
Only set confirm true if the user explicitly confirms the pending booking details.
If the user changes a field, set confirm false. Treat booking continuation as booking intent.
If a booking is pending and the user asks a separate question, use qa/history appropriately.
Never claim a booking was created; the server executes the booking tool.''' 

@app.post('/api/chat', response_model=ChatOut)
def chat(request: ChatIn):
    state = state_get(request.session_id)
    patient = rows('SELECT * FROM patients WHERE patient_id=:pid', pid=request.patient_id)[0]
    visits = rows('SELECT * FROM patient_treatment_history WHERE patient_id=:pid', pid=request.patient_id)
    current_bookings = bookings(request.patient_id)
    context = {'today': date.today().isoformat(), 'patient': patient, 'past_visits': visits,
               'catalog': catalog(), 'bookings': current_bookings,
               'pending_booking': state['pending'], 'recent_messages': state['history'][-6:],
               'user_message': request.message}
    result = llm_json(SYSTEM, json.dumps(context, ensure_ascii=False))
    intent = result.get('intent', 'qa')
    pending = state['pending']
    if intent == 'cancel':
        state['pending'] = {}
        reply = 'The unfinished booking request has been cleared. Existing appointments were not changed.'
    elif intent == 'history':
        upcoming = [b for b in current_bookings if b['booking_date'] >= date.today().isoformat() and b['status'] == 'Confirmed']
        if upcoming:
            reply = 'Your upcoming appointments:\n' + '\n'.join(
                f"• {b['booking_date']} {b['booking_time'][:5]} — {b['doctor_name']}, {b['treatment_name']} (#{b['booking_id']})" for b in upcoming)
        else:
            reply = 'You have no upcoming confirmed appointments.'
    elif intent == 'booking':
        for key in ('doctor_id','treatment_id','booking_date','booking_time'):
            if result.get(key) is not None:
                pending[key] = str(result[key])
        state['pending'] = pending
        docs = {d['doctor_id']:d for d in context['catalog']['doctors']}
        treatments = {t['treatment_id']:t for t in context['catalog']['treatments']}
        if pending.get('doctor_id') not in docs: pending.pop('doctor_id', None)
        if pending.get('treatment_id') not in treatments: pending.pop('treatment_id', None)
        missing = [k for k in ('doctor_id','treatment_id','booking_date','booking_time') if not pending.get(k)]
        if missing:
            prompts = {'doctor_id':'which doctor', 'treatment_id':'which treatment',
                       'booking_date':'which date', 'booking_time':'what time'}
            reply = 'To arrange the appointment, please tell me ' + ', '.join(prompts[k] for k in missing) + '.'
        else:
            summary = (f"{treatments[pending['treatment_id']]['treatment_name']} with "
                       f"{docs[pending['doctor_id']]['full_name']} on {pending['booking_date']} "
                       f"at {pending['booking_time']}")
            if result.get('confirm'):
                try:
                    booking_data = BookingIn(patient_id=request.patient_id, **pending)
                    # Agent tool: invoke the REST endpoint through the in-process ASGI transport.
                    # This preserves one validation/persistence path and avoids localhost self-requests.
                    from fastapi.testclient import TestClient
                    with TestClient(app) as client:
                        tool_response = client.post('/api/bookings', json=booking_data.model_dump(mode='json'))
                    if tool_response.status_code != 201:
                        reply = f"Booking was not saved: {tool_response.json().get('detail', 'validation error')}. Please correct the details."
                    else:
                        booked = tool_response.json()
                        state['pending'] = {}
                        state['history'] = (state['history'] + [{'user':request.message,'assistant':summary}])[-6:]
                        state_put(request.session_id, state)
                        return ChatOut(reply=f"Confirmed and saved: {summary}. Booking ID: {booked['booking_id']}.",
                                       intent='booking', booked=True, booking=booked)
                except (ValueError, TypeError) as e:
                    reply = f'Invalid booking details: {e}. Please provide a valid future date and HH:MM time.'
            else:
                reply = f'Please confirm this appointment: {summary}. Reply "confirm" to save it.'
    else:
        reply = str(result.get('reply') or 'Could you rephrase your question?')
    state['history'] = (state['history'] + [{'user':request.message,'assistant':reply}])[-6:]
    state_put(request.session_id, state)
    return ChatOut(reply=reply, intent=intent)
