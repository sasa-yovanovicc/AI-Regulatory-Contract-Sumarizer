import React, { useState } from 'react';
import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

type Task = 'summary' | 'unfavorable_elements' | 'conflicts';

const tasks: { value: Task; label: string; example: string }[] = [
  { value: 'summary', label: 'Summary', example: 'Summarize in 3 sentences for banking officer' },
  { value: 'unfavorable_elements', label: 'Unfavorable Clauses', example: 'Find unfavorable contract elements' },
  { value: 'conflicts', label: 'Conflicts', example: 'Find conflicting sections' },
];

export default function App() {
  const [text, setText] = useState('');
  const [focus, setFocus] = useState('');
  const [task, setTask] = useState<Task>('summary');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<string>('');
  const [progress, setProgress] = useState<{processed:number,total:number}|null>(null);
  const [partials, setPartials] = useState<string[]>([]);
  const [modeStream, setModeStream] = useState<boolean>(true);
  const [file, setFile] = useState<File | null>(null);

  const submit = async () => {
    setLoading(true);
    setResult('');
    setProgress(null);
    setPartials([]);
    try {
      if (modeStream) {
        if (file) {
          const form = new FormData();
            form.append('file', file);
            form.append('task', task);
            if (focus) form.append('focus', focus);
            const resp = await fetch(`${API_BASE}/summarize-pdf-stream`, { method: 'POST', body: form });
            await handleStream(resp);
        } else {
          const resp = await fetch(`${API_BASE}/summarize-stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text, task, focus: focus || undefined })
          });
          await handleStream(resp);
        }
      } else {
        if (file) {
          const form = new FormData();
          form.append('file', file);
          form.append('task', task);
          if (focus) form.append('focus', focus);
          const r = await axios.post(`${API_BASE}/summarize-pdf`, form, { headers: { 'Content-Type': 'multipart/form-data' }});
          setResult(r.data.final);
        } else {
          const r = await axios.post(`${API_BASE}/summarize`, { text, task, focus: focus || undefined });
          setResult(r.data.final);
        }
      }
    } catch (e: any) {
      setResult(`Error: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  async function handleStream(resp: Response) {
    if (!resp.ok) {
      const errorText = await resp.text();
      setResult(`Error: HTTP ${resp.status} - ${errorText}`);
      return;
    }
    
    const data = await resp.json();
    
    // Handle new "complete" response format (non-streaming)
    if (data.type === 'complete') {
      setResult(data.final);
      setPartials(data.partial || []);
      setProgress({ processed: data.chunks, total: data.chunks });
      return;
    }
    
    // Handle old streaming format (if we restore it later)
    const reader = resp.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, idx).trim();
        buffer = buffer.slice(idx + 1);
        if (!line) continue;
        try {
          const evt = JSON.parse(line);
          console.debug('event', evt);
          if (evt.type === 'meta') {
            setProgress({ processed: 0, total: evt.chunks });
          } else if (evt.type === 'chunk') {
            setPartials(p => [...p, evt.content]);
            setProgress({ processed: evt.processed, total: evt.total });
          } else if (evt.type === 'final') {
            setResult(evt.final);
            setProgress({ processed: evt.processed, total: evt.total });
          } else if (evt.type === 'error') {
            setResult(r => r + `\n[Error] ${evt.message || evt.chunk}`);
          }
        } catch { /* ignore parse errors */ }
      }
    }
  }

  return (
    <div style={{ fontFamily: 'system-ui', padding: '1.5rem', maxWidth: 960, margin: '0 auto' }}>
      <h1>Regulatory Summarizer</h1>
      <p style={{ color: '#555' }}>Upload a PDF or paste text. Choose analysis task. All LLM calls are server-side.</p>
  <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
        {tasks.map(t => (
          <button
            key={t.value}
            onClick={() => setTask(t.value)}
            style={{
              padding: '0.5rem 0.9rem',
              borderRadius: 6,
              border: task === t.value ? '2px solid #2563eb' : '1px solid #ccc',
              background: task === t.value ? '#eff6ff' : '#f8f8f8',
              cursor: 'pointer'
            }}
            title={t.example}
          >
            {t.label}
          </button>
        ))}
      </div>
      <label style={{ display: 'block', marginTop: '1rem', fontWeight: 600 }}>Optional focus</label>
      <input value={focus} onChange={e => setFocus(e.target.value)} placeholder="e.g. data protection" style={{ width: '100%', padding: '0.5rem' }} />
      <div style={{ marginTop: '0.75rem' }}>
        <label style={{ fontWeight: 600 }}>Mode: </label>
        <label><input type="radio" checked={modeStream} onChange={()=>setModeStream(true)} /> Streaming</label>{' '}
        <label><input type="radio" checked={!modeStream} onChange={()=>setModeStream(false)} /> One-shot</label>
      </div>
      <label style={{ display: 'block', marginTop: '1rem', fontWeight: 600 }}>Paste text (if not uploading PDF)</label>
      <textarea value={text} onChange={e => setText(e.target.value)} rows={8} placeholder="Paste regulatory text..." style={{ width: '100%', padding: '0.75rem', fontFamily: 'monospace' }} />
      <div style={{ marginTop: '1rem' }}>
        <input type="file" accept="application/pdf" onChange={e => setFile(e.target.files?.[0] || null)} />
        {file && <span style={{ marginLeft: 8 }}>{file.name}</span>}
      </div>
      <button disabled={loading || (!text && !file)} onClick={submit} style={{ marginTop: '1.25rem', padding: '0.75rem 1.25rem', background: '#2563eb', color: 'white', border: 'none', borderRadius: 6, cursor: 'pointer' }}>
        {loading ? (progress ? `Processing ${progress.processed}/${progress.total}` : 'Processing...') : 'Run'}
      </button>
      {progress && (
        <div style={{ marginTop: '0.75rem', fontSize: 12 }}>
          Progress: {progress.processed}/{progress.total}
          <div style={{ height: 6, background: '#eee', borderRadius: 3, marginTop: 4 }}>
            <div style={{ width: `${(progress.processed/Math.max(progress.total,1))*100}%`, background: '#2563eb', height: '100%', borderRadius: 3 }} />
          </div>
        </div>
      )}
      <div style={{ marginTop: '2rem' }}>
        <h2>Result</h2>
        {partials.length > 0 && (
          <details open style={{ marginBottom: '1rem' }}>
            <summary style={{ cursor: 'pointer' }}>Partial chunks ({partials.length})</summary>
            <ul>
              {partials.map((p,i)=>(<li key={i} style={{ marginBottom: 4 }}>{p}</li>))}
            </ul>
          </details>
        )}
        <pre style={{ whiteSpace: 'pre-wrap', background: '#f5f5f5', padding: '1rem', borderRadius: 8, minHeight: 160 }}>{result}</pre>
      </div>
      <footer style={{ marginTop: '2rem', fontSize: 12, color: '#777' }}>
        Demo app – not legal advice.
      </footer>
    </div>
  );
}
