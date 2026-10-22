import os
import tempfile
from datetime import date, timedelta
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_seed_and_patient_bookings():
    r = client.get('/api/bookings')
    assert r.status_code == 200
    assert any(b['booking_id'] == 'B1001' for b in r.json())
    assert all(b['patient_id'] == 'P001' for b in r.json())

def test_booking_persists():
    future = (date.today() + timedelta(days=7)).isoformat()
    r = client.post('/api/bookings', json={'patient_id':'P001','doctor_id':'D101','treatment_id':'T001','booking_date':future,'booking_time':'10:00'})
    assert r.status_code == 201, r.text
    bid = r.json()['booking_id']
    assert any(b['booking_id'] == bid for b in client.get('/api/bookings').json())

def test_invalid_doctor_rejected():
    r = client.post('/api/bookings', json={'doctor_id':'FAKE','treatment_id':'T001','booking_date':(date.today()+timedelta(days=1)).isoformat(),'booking_time':'10:00'})
    assert r.status_code == 422

def test_multiturn_agent_with_stub(monkeypatch):
    from app import main
    responses = iter([
        {'intent':'booking','doctor_id':'D101','treatment_id':'T001','booking_date':None,'booking_time':None,'confirm':False},
        {'intent':'booking','doctor_id':None,'treatment_id':None,'booking_date':(date.today()+timedelta(days=8)).isoformat(),'booking_time':'11:00','confirm':False},
        {'intent':'booking','doctor_id':None,'treatment_id':None,'booking_date':None,'booking_time':None,'confirm':True},
    ])
    monkeypatch.setattr(main, 'llm_json', lambda *_: next(responses))
    sid='test-'+__import__('uuid').uuid4().hex
    def send(message):
        return client.post('/api/chat', json={'message':message,'session_id':sid})
    assert 'date' in send('Book checkup with Dr Sarah').json()['reply']
    assert 'confirm' in send('Next week at 11').json()['reply'].lower()
    r=send('confirm')
    assert r.status_code==200, r.text
    assert r.json()['booked'] is True
    assert any(b['booking_id']==r.json()['booking']['booking_id'] for b in client.get('/api/bookings').json())
