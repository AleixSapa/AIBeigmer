const API = '/api';

function setupNavigation() {
  const buttons = document.querySelectorAll('#nav button');
  const pages = document.querySelectorAll('.page');
  buttons.forEach(button => button.addEventListener('click', () => {
    const target = button.dataset.page;
    buttons.forEach(item => item.classList.toggle('active', item === button));
    pages.forEach(page => page.classList.toggle('active', page.dataset.section === target));
    history.replaceState(null, '', `#${target}`);
  }));

  const hash = location.hash.slice(1);
  if (hash && document.querySelector(`[data-page="${hash}"]`)) {
    document.querySelector(`[data-page="${hash}"]`).click();
  }
}

async function loadDashboard() {
  try {
    const [statsResponse, categoriesResponse] = await Promise.all([
      fetch(`${API}/stats`), fetch(`${API}/categories`)
    ]);
    if (!statsResponse.ok || !categoriesResponse.ok) throw new Error('API error');
    const stats = await statsResponse.json();
    const categories = await categoriesResponse.json();
    document.querySelector('#status').textContent = 'API connectada';
    document.querySelector('#avg-score').textContent = stats.average_score ?? '—';
    document.querySelector('#leader').textContent = stats.leader ?? '—';
    document.querySelector('#runs').textContent = stats.executions ?? 0;
    document.querySelector('#fastest').textContent = stats.fastest_model ?? '—';
    document.querySelector('#categories').innerHTML = categories.map(category => `
      <button class="category-card" data-category="${category.id}">
        <strong>${category.name}</strong><span>${category.question_count} preguntes</span>
      </button>`).join('');
  } catch (error) {
    document.querySelector('#status').textContent = 'Backend no disponible';
    document.querySelector('#categories').innerHTML = '<p>No s’ha pogut connectar amb l’API.</p>';
  }
}

setupNavigation();
loadDashboard();
