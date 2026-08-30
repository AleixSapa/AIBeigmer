const API = '/api';
const titles = {dashboard:'Dashboard',models:'Models',benchmarks:'Benchmarks',execute:'Executar',results:'Resultats',compare:'Comparar',ranking:'Rànquing',settings:'Configuració'};

function showPage(page){
  if(!titles[page]) page='dashboard';
  document.querySelectorAll('.page').forEach(x=>x.classList.toggle('active',x.dataset.section===page));
  document.querySelectorAll('#nav button').forEach(x=>x.classList.toggle('active',x.dataset.page===page));
  document.querySelector('#page-title').textContent=titles[page];
  history.replaceState(null,'',`#${page}`);
}

document.addEventListener('click',e=>{const b=e.target.closest('[data-page]');if(b)showPage(b.dataset.page)});
window.addEventListener('hashchange',()=>showPage(location.hash.slice(1)));
showPage(location.hash.slice(1) || 'dashboard');

async function loadDashboard(){
  const status=document.querySelector('#status');
  try{
    const response=await fetch(`${API}/stats`,{headers:{Accept:'application/json'}});
    if(!response.ok) throw new Error();
    const stats=await response.json();
    status.textContent='● API connectada';
    document.querySelector('#avg-score').textContent=stats.average_score ?? '—';
    document.querySelector('#leader').textContent=stats.leader ?? '—';
    document.querySelector('#runs').textContent=stats.executions ?? 0;
    document.querySelector('#fastest').textContent=stats.fastest_model ?? '—';
  }catch{
    // The UI remains fully usable when the API is offline.
    status.textContent='○ Mode local';
    document.querySelector('#categories').innerHTML=`<div class="category-card"><strong>Backend offline</strong><span>Connecta FastAPI per carregar dades</span></div>`;
  }
}
loadDashboard();