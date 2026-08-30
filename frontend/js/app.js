const API = '/api';

async function loadDashboard() {
  try {
    const response = await fetch(`${API}/stats`);
    if (!response.ok) throw new Error('API unavailable');
    const stats = await response.json();
    document.querySelector('#status').textContent = 'API connectada';
    document.querySelector('#avg-score').textContent = stats.average_score ?? '—';
    document.querySelector('#leader').textContent = stats.leader ?? '—';
    document.querySelector('#runs').textContent = stats.executions ?? 0;
    document.querySelector('#fastest').textContent = stats.fastest_model ?? '—';
  } catch {
    document.querySelector('#status').textContent = 'API pendent de configurar';
  }
}
loadDashboard();
