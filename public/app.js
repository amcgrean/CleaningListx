const authCard = document.getElementById('auth-card');
const schedule = document.getElementById('schedule');
const authForm = document.getElementById('auth-form');
const weekLabel = document.getElementById('week-label');
const weeklyGrid = document.getElementById('weekly-grid');
const monthlyList = document.getElementById('monthly-list');
const annualList = document.getElementById('annual-list');
const monthTrack = document.getElementById('month-track');
const whoami = document.getElementById('whoami');

let tasks = [];
let completions = {};
let currentWeekStart = getWeekStart(new Date());
let authProvider = 'local';

function getStoredToken() {
  return localStorage.getItem('neonAuthToken') || '';
}

function setStoredToken(token) {
  if (token) localStorage.setItem('neonAuthToken', token);
  else localStorage.removeItem('neonAuthToken');
}

function getWeekStart(date) {
  const d = new Date(date);
  const day = d.getDay();
  const diff = (day + 6) % 7;
  d.setDate(d.getDate() - diff);
  d.setHours(0, 0, 0, 0);
  return d;
}

function formatWeek(date) {
  return date.toISOString().slice(0, 10);
}

function weekLabelText(start) {
  const end = new Date(start);
  end.setDate(end.getDate() + 6);
  return `${start.toLocaleDateString()} - ${end.toLocaleDateString()}`;
}

async function api(url, options = {}) {
  const token = getStoredToken();
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(url, {
    ...options,
    headers
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Request failed');
  return data;
}

function taskChecked(taskId) {
  return Boolean(completions[taskId]);
}

function renderWeekly() {
  const order = ['Daily', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
  weeklyGrid.innerHTML = '';
  order.forEach((section) => {
    const sectionTasks = tasks.filter((t) => t.section === section);
    if (!sectionTasks.length) return;

    const card = document.createElement('article');
    card.className = 'day-card';
    card.dataset.theme = section;
    card.innerHTML = `<div class="day-title">${section}</div>`;

    sectionTasks.forEach((task) => {
      const row = document.createElement('label');
      row.className = 'task-row';
      row.innerHTML = `
        <span>${task.label}</span>
        <input type="checkbox" ${taskChecked(task.id) ? 'checked' : ''} data-id="${task.id}" />`;
      card.appendChild(row);
    });

    weeklyGrid.appendChild(card);
  });
}

function renderMonthly() {
  monthlyList.innerHTML = '';
  tasks
    .filter((t) => t.frequency === 'monthly')
    .forEach((task) => {
      const row = document.createElement('label');
      row.className = 'month-row';
      row.innerHTML = `<span>${task.label}</span><input type="checkbox" ${taskChecked(task.id) ? 'checked' : ''} data-id="${task.id}"/>`;
      monthlyList.appendChild(row);
    });
}

function renderAnnual() {
  annualList.innerHTML = '';
  tasks
    .filter((t) => t.frequency === 'annual')
    .forEach((task) => {
      const row = document.createElement('label');
      row.className = 'annual-row';
      const marker = task.section.replace('Annual ', '');
      row.innerHTML = `<span><strong>${marker}</strong> ${task.label}</span><input type="checkbox" ${taskChecked(task.id) ? 'checked' : ''} data-id="${task.id}"/>`;
      annualList.appendChild(row);
    });
}

function renderTrack() {
  const monthChars = ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D'];
  monthTrack.innerHTML = '';
  for (let r = 0; r < 8; r += 1) {
    monthChars.forEach((char, c) => {
      const cell = document.createElement('div');
      cell.className = 'month-cell';
      cell.textContent = r === 0 ? char : '';
      const hue = 12 + c * 15;
      cell.style.background = `hsl(${hue} 48% ${r === 0 ? '72%' : '84%'})`;
      monthTrack.appendChild(cell);
    });
  }
}

async function loadCompletionsAndRender() {
  const weekStart = formatWeek(currentWeekStart);
  weekLabel.textContent = weekLabelText(currentWeekStart);
  const data = await api(`/api/completions?weekStart=${weekStart}`);
  completions = data.completions;
  renderWeekly();
  renderMonthly();
  renderAnnual();
  renderTrack();
}

async function toggleCompletion(taskId, completed) {
  await api('/api/completions', {
    method: 'POST',
    body: JSON.stringify({ weekStart: formatWeek(currentWeekStart), taskId, completed })
  });
}

function authMessageEl() {
  return document.getElementById('auth-message');
}

function setNeonAuthMode() {
  authForm.innerHTML = `
    <label>
      Neon access token (JWT)
      <input id="token-input" name="token" required placeholder="Paste Neon JWT" />
    </label>
    <div class="auth-actions">
      <button type="button" data-mode="token-login">Continue</button>
    </div>
    <p id="auth-message"></p>`;
}

document.addEventListener('change', async (event) => {
  const input = event.target;
  if (!(input instanceof HTMLInputElement) || input.type !== 'checkbox' || !input.dataset.id) return;
  const id = Number(input.dataset.id);
  completions[id] = input.checked;
  try {
    await toggleCompletion(id, input.checked);
  } catch (error) {
    input.checked = !input.checked;
    completions[id] = input.checked;
    alert(error.message);
  }
});

authForm.addEventListener('click', async (event) => {
  const button = event.target;
  if (!(button instanceof HTMLButtonElement) || !button.dataset.mode) return;

  if (button.dataset.mode === 'token-login') {
    const tokenInput = document.getElementById('token-input');
    if (!(tokenInput instanceof HTMLInputElement) || !tokenInput.value.trim()) {
      authMessageEl().textContent = 'Provide a Neon JWT.';
      return;
    }

    setStoredToken(tokenInput.value.trim());
    try {
      const me = await api('/api/auth/me');
      if (!me.user) throw new Error('Invalid token.');
      whoami.textContent = me.user.username;
      authCard.classList.add('hidden');
      schedule.classList.remove('hidden');
      tasks = (await api('/api/tasks')).tasks;
      await loadCompletionsAndRender();
      authMessageEl().textContent = '';
    } catch (error) {
      setStoredToken('');
      authMessageEl().textContent = error.message;
    }
    return;
  }

  const formData = new FormData(authForm);
  const payload = {
    username: formData.get('username'),
    password: formData.get('password')
  };

  try {
    const endpoint = button.dataset.mode === 'register' ? '/api/auth/register' : '/api/auth/login';
    const sessionData = await api(endpoint, { method: 'POST', body: JSON.stringify(payload) });
    whoami.textContent = sessionData.username;
    authCard.classList.add('hidden');
    schedule.classList.remove('hidden');
    tasks = (await api('/api/tasks')).tasks;
    await loadCompletionsAndRender();
  } catch (error) {
    authMessageEl().textContent = error.message;
  }
});

async function bootstrap() {
  const cfg = await api('/api/auth/config');
  authProvider = cfg.provider;

  if (authProvider === 'neon') {
    setNeonAuthMode();
  }

  const me = await api('/api/auth/me');
  if (!me.user) return;

  whoami.textContent = me.user.username;
  authCard.classList.add('hidden');
  schedule.classList.remove('hidden');
  tasks = (await api('/api/tasks')).tasks;
  await loadCompletionsAndRender();
}

document.getElementById('prev-week').addEventListener('click', async () => {
  currentWeekStart.setDate(currentWeekStart.getDate() - 7);
  currentWeekStart = new Date(currentWeekStart);
  await loadCompletionsAndRender();
});

document.getElementById('next-week').addEventListener('click', async () => {
  currentWeekStart.setDate(currentWeekStart.getDate() + 7);
  currentWeekStart = new Date(currentWeekStart);
  await loadCompletionsAndRender();
});

document.getElementById('logout').addEventListener('click', async () => {
  if (authProvider === 'neon') {
    setStoredToken('');
    location.reload();
    return;
  }

  await api('/api/auth/logout', { method: 'POST' });
  location.reload();
});

bootstrap().catch((error) => {
  authMessageEl().textContent = error.message;
});
