const authCard = document.getElementById('auth-card');
const schedule = document.getElementById('schedule');
const authForm = document.getElementById('auth-form');
const weekLabel = document.getElementById('week-label');
const weeklyGrid = document.getElementById('weekly-grid');
const monthlyList = document.getElementById('monthly-list');
const annualList = document.getElementById('annual-list');
const monthTrack = document.getElementById('month-track');
const whoami = document.getElementById('whoami');
const householdPanel = document.getElementById('household-panel');

let tasks = [];
let completions = {};
let currentWeekStart = getWeekStart(new Date());
let authProvider = 'local';
let household = null;
let householdCompletions = {};
let householdMembers = [];
const weekdayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const MEMBER_COLORS = ['#e07a5f', '#81b29a', '#6d6875', '#f2cc8f', '#b5838d', '#3d405b', '#a8dadc'];

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

function getMemberColor(index) {
  return MEMBER_COLORS[index % MEMBER_COLORS.length];
}

function renderMemberAvatars(taskId) {
  if (!household || householdMembers.length <= 1) return '';
  const taskComp = householdCompletions[taskId] || {};
  return householdMembers.map((member, idx) => {
    const done = Boolean(taskComp[member.id]);
    const color = getMemberColor(idx);
    const initial = (member.username[0] || '?').toUpperCase();
    return `<span class="member-avatar${done ? ' done' : ''}" title="${member.username}: ${done ? 'done' : 'not done'}" style="--avatar-color:${color}">${initial}</span>`;
  }).join('');
}

function getDefaultOpenSections() {
  const today = weekdayNames[new Date().getDay()];
  return new Set(['Daily', today]);
}

function setDayCardExpanded(card, expanded) {
  card.classList.toggle('is-collapsed', !expanded);
  const toggle = card.querySelector('.day-toggle');
  if (toggle) toggle.setAttribute('aria-expanded', String(expanded));
}

function renderWeekly() {
  const order = ['Daily', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
  const defaultOpenSections = getDefaultOpenSections();
  weeklyGrid.innerHTML = '';
  order.forEach((section) => {
    const sectionTasks = tasks.filter((t) => t.section === section);
    if (!sectionTasks.length) return;

    const card = document.createElement('article');
    card.className = 'day-card';
    card.dataset.theme = section;
    card.innerHTML = `
      <button type="button" class="day-toggle" aria-expanded="false">${section}</button>
      <div class="day-tasks"></div>`;

    const tasksContainer = card.querySelector('.day-tasks');

    sectionTasks.forEach((task) => {
      const row = document.createElement('label');
      row.className = 'task-row';
      row.innerHTML = `
        <span>${task.label}</span>
        <span class="task-avatars">${renderMemberAvatars(task.id)}</span>
        <input type="checkbox" ${taskChecked(task.id) ? 'checked' : ''} data-id="${task.id}" />`;
      tasksContainer.appendChild(row);
    });

    const expandedByDefault = defaultOpenSections.has(section);
    setDayCardExpanded(card, expandedByDefault);

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
      row.innerHTML = `<span>${task.label}</span><span class="task-avatars">${renderMemberAvatars(task.id)}</span><input type="checkbox" ${taskChecked(task.id) ? 'checked' : ''} data-id="${task.id}"/>`;
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
      row.innerHTML = `<span><strong>${marker}</strong> ${task.label}</span><span class="task-avatars">${renderMemberAvatars(task.id)}</span><input type="checkbox" ${taskChecked(task.id) ? 'checked' : ''} data-id="${task.id}"/>`;
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

  if (household) {
    const hhData = await api(`/api/household/completions?weekStart=${weekStart}`);
    householdCompletions = hhData.completions;
    householdMembers = hhData.members;
  } else {
    householdCompletions = {};
    householdMembers = [];
  }

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

// --- Household panel ---

function renderHouseholdPanel() {
  if (!household) {
    householdPanel.innerHTML = `
      <div class="household-inner">
        <h3>Family Household</h3>
        <p class="hh-desc">Create a household to share your cleaning list and track who completed each task.</p>
        <div class="household-forms">
          <div class="household-form-block">
            <h4>Create a household</h4>
            <label>Name<input id="hh-name" placeholder="e.g. The Smith Family" /></label>
            <button id="hh-create-btn">Create</button>
          </div>
          <div class="household-form-block">
            <h4>Join a household</h4>
            <label>Invite code<input id="hh-code" placeholder="Enter 8-character code" /></label>
            <button id="hh-join-btn">Join</button>
          </div>
        </div>
        <p id="hh-message" class="hh-message"></p>
      </div>`;
  } else {
    const isOwner = household.role === 'owner';
    const memberList = (household.members || []).map((m, idx) => {
      const color = getMemberColor(idx);
      const initial = (m.username[0] || '?').toUpperCase();
      const badge = m.role === 'owner' ? ' <em>(owner)</em>' : '';
      return `<li><span class="member-avatar done" style="--avatar-color:${color}">${initial}</span>${m.username}${badge}</li>`;
    }).join('');

    householdPanel.innerHTML = `
      <div class="household-inner">
        <div class="hh-header">
          <h3>${household.name}</h3>
          <button id="hh-leave-btn" class="secondary">Leave</button>
        </div>
        <ul class="members-list">${memberList}</ul>
        ${isOwner ? `
        <div class="invite-code-box">
          <span>Invite code:</span>
          <code>${household.invite_code}</code>
          <button id="hh-copy-btn" class="secondary">Copy</button>
        </div>
        <p class="hh-desc">Share this code with family members so they can join.</p>
        ` : ''}
        <p id="hh-message" class="hh-message"></p>
      </div>`;
  }
}

function hhMessage(text) {
  const el = document.getElementById('hh-message');
  if (el) el.textContent = text;
}

householdPanel.addEventListener('click', async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLButtonElement)) return;

  if (target.id === 'hh-create-btn') {
    const nameInput = document.getElementById('hh-name');
    const name = (nameInput instanceof HTMLInputElement ? nameInput.value : '').trim();
    if (!name) { hhMessage('Please enter a household name.'); return; }
    try {
      const result = await api('/api/household/create', { method: 'POST', body: JSON.stringify({ name }) });
      household = { ...result, members: [{ id: 0, username: whoami.textContent, role: 'owner' }] };
      const fresh = await api('/api/household');
      household = fresh.household;
      renderHouseholdPanel();
      await loadCompletionsAndRender();
    } catch (err) {
      hhMessage(err.message);
    }
    return;
  }

  if (target.id === 'hh-join-btn') {
    const codeInput = document.getElementById('hh-code');
    const inviteCode = (codeInput instanceof HTMLInputElement ? codeInput.value : '').trim().toUpperCase();
    if (!inviteCode) { hhMessage('Please enter an invite code.'); return; }
    try {
      await api('/api/household/join', { method: 'POST', body: JSON.stringify({ inviteCode }) });
      const fresh = await api('/api/household');
      household = fresh.household;
      renderHouseholdPanel();
      await loadCompletionsAndRender();
    } catch (err) {
      hhMessage(err.message);
    }
    return;
  }

  if (target.id === 'hh-leave-btn') {
    if (!confirm('Leave this household?')) return;
    try {
      await api('/api/household/leave', { method: 'DELETE' });
      household = null;
      householdCompletions = {};
      householdMembers = [];
      renderHouseholdPanel();
      await loadCompletionsAndRender();
    } catch (err) {
      hhMessage(err.message);
    }
    return;
  }

  if (target.id === 'hh-copy-btn') {
    if (household && household.invite_code) {
      try {
        await navigator.clipboard.writeText(household.invite_code);
        target.textContent = 'Copied!';
        setTimeout(() => { target.textContent = 'Copy'; }, 2000);
      } catch {
        hhMessage('Could not copy — invite code: ' + household.invite_code);
      }
    }
  }
});

// --- Auth form ---

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
  // Update household completions optimistically for current user
  if (household) {
    const myId = householdMembers.find((m) => m.username === whoami.textContent)?.id;
    if (myId != null) {
      if (!householdCompletions[id]) householdCompletions[id] = {};
      householdCompletions[id][myId] = input.checked;
      // Re-render just the avatars for this task
      document.querySelectorAll(`.task-avatars`).forEach((el) => {
        const row = el.closest('[data-id]') || el.parentElement;
        const taskId = Number(el.parentElement.querySelector('input[data-id]')?.dataset.id);
        if (taskId === id) el.innerHTML = renderMemberAvatars(id);
      });
    }
  }
  try {
    await toggleCompletion(id, input.checked);
  } catch (error) {
    input.checked = !input.checked;
    completions[id] = input.checked;
    alert(error.message);
  }
});

document.addEventListener('click', (event) => {
  const target = event.target;
  if (!(target instanceof HTMLButtonElement) || !target.classList.contains('day-toggle')) return;

  const card = target.closest('.day-card');
  if (!card) return;
  const isExpanded = target.getAttribute('aria-expanded') === 'true';
  setDayCardExpanded(card, !isExpanded);
});

document.getElementById('household-btn').addEventListener('click', () => {
  householdPanel.classList.toggle('hidden');
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
      const hhData = await api('/api/household');
      household = hhData.household;
      renderHouseholdPanel();
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
    const hhData = await api('/api/household');
    household = hhData.household;
    renderHouseholdPanel();
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
  const hhData = await api('/api/household');
  household = hhData.household;
  renderHouseholdPanel();
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
