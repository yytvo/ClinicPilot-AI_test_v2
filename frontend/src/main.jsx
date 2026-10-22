import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
function App() {
  const [messages,setMessages]=useState([{who:'assistant',text:'Hello John! I can answer clinic questions, recommend services, check appointments, and book visits.'}]);
  const [input,setInput]=useState(''); const [busy,setBusy]=useState(false);
  const [bookings,setBookings]=useState([]); const [error,setError]=useState('');
  const [session]=useState(()=>{let s=sessionStorage.getItem('clinicpilot_session');if(!s){s=crypto.randomUUID();sessionStorage.setItem('clinicpilot_session',s)}return s});
  async function refresh(){try{const r=await fetch('/api/bookings');if(!r.ok)throw Error('Cannot load bookings');setBookings(await r.json())}catch(e){setError(e.message)}}
  useEffect(()=>{refresh()},[]);
  async function send(e){e.preventDefault();const msg=input.trim();if(!msg||busy)return;setInput('');setError('');setBusy(true);setMessages(m=>[...m,{who:'user',text:msg}]);
    try{const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:msg,session_id:session})});const data=await r.json();if(!r.ok)throw Error(data.detail||'Chat request failed');setMessages(m=>[...m,{who:'assistant',text:data.reply}]);if(data.booked)await refresh()}
    catch(e){setError(String(e.message))}finally{setBusy(false)}}
  return <main><header><h1>ClinicPilot AI</h1><span>Demo patient: John Doe (P001)</span></header><div className="layout"><section><h2>Clinic assistant</h2><div className="messages">{messages.map((m,i)=><div className={'bubble '+m.who} key={i}><small>{m.who==='user'?'You':'ClinicPilot'}</small><p>{m.text}</p></div>)}{busy&&<p>Assistant is thinking…</p>}</div><form onSubmit={send}><input value={input} onChange={e=>setInput(e.target.value)} placeholder="Ask about doctors, appointments, or book a visit"/><button disabled={busy}>Send</button></form>{error&&<p className="error">{error}</p>}</section><section><div className="between"><h2>Patient bookings</h2><button onClick={refresh}>Refresh</button></div><table><thead><tr><th>Date / Time</th><th>Doctor</th><th>Treatment</th><th>Status</th></tr></thead><tbody>{bookings.map(b=><tr key={b.booking_id}><td>{b.booking_date}<br/>{b.booking_time}</td><td>{b.doctor_name}</td><td>{b.treatment_name}</td><td>{b.status}</td></tr>)}</tbody></table></section></div><footer>Prototype only · Not medical advice · In emergencies call local emergency services.</footer></main>
}
createRoot(document.getElementById('root')).render(<App/>);
