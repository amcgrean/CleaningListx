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
const settingsPanel = document.getElementById('settings-panel');

let tasks = [];
let completions = {};
let currentWeekStart = getWeekStart(new Date());
let authProvider = 'local';
let household = null;
let householdCompletions = {};
let householdMembers = [];
let settingsActiveTab = 'weekly';
const weekdayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const MEMBER_COLORS = ['#e07a5f', '#81b29a', '#6d6875', '#f2cc8f', '#b5838d', '#3d405b', '#a8dadc'];
const MONTH_LETTERS = ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D'];
const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const WEEKLY_SECTION_ORDER = ['Daily', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

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
    const sectionTasks = tasks.filter((t) => t.section === section).sort((a, b) => a.sort_order - b.sort_order);
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
    .sort((a, b) => a.sort_order - b.sort_order)
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
    .sort((a, b) => a.sort_order - b.sort_order)
    .forEach((task) => {
      const row = document.createElement('label');
      row.className = 'annual-row';
      const monthNum = parseInt(task.section.replace('Annual ', ''), 10);
      const marker = (!isNaN(monthNum) && monthNum >= 1 && monthNum <= 12)
        ? MONTH_LETTERS[monthNum - 1]
        : task.section.replace('Annual ', '');
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

// --- Helpers ---

function esc(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function getFrequency(section) {
  if (section.startsWith('Annual')) return 'annual';
  if (section === 'Monthly') return 'monthly';
  return 'weekly';
}

// --- Settings panel ---

function allSectionsOptions(currentSection) {
  const weekly = WEEKLY_SECTION_ORDER;
  const annual = Array.from({ length: 12 }, (_, i) => `Annual ${i + 1}`);
  const sections = [...weekly, 'Monthly', ...annual];
  return sections.map((s) => {
    let label = s;
    if (s.startsWith('Annual ')) {
      const n = parseInt(s.replace('Annual ', ''), 10);
      label = (n >= 1 && n <= 12) ? MONTH_NAMES[n - 1] : s;
    }
    return `<option value="${esc(s)}"${s === currentSection ? ' selected' : ''}>${esc(label)}</option>`;
  }).join('');
}

function renderSettingsTaskRow(task, idx, total) {
  return `
    <div class="settings-task-row" data-task-id="${task.id}">
      <button class="move-btn move-up" title="Move up"${idx === 0 ? ' disabled' : ''}>▲</button>
      <button class="move-btn move-down" title="Move down"${idx === total - 1 ? ' disabled' : ''}>▼</button>
      <input type="text" class="task-label-input" value="${esc(task.label)}" />
      <select class="task-section-select" title="Change section">${allSectionsOptions(task.section)}</select>
      <button class="delete-task-btn" title="Delete task">✕</button>
    </div>`;
}

function renderSettingsSection(section, headerLabel) {
  const sectionTasks = tasks.filter((t) => t.section === section).sort((a, b) => a.sort_order - b.sort_order);
  const rows = sectionTasks.map((task, idx) => renderSettingsTaskRow(task, idx, sectionTasks.length)).join('');
  const placeholder = section.startsWith('Annual ')
    ? `Add task for ${allSectionsOptions(section).match(/selected[^>]*>([^<]+)/)?.[1] || section}...`
    : `Add task to ${section}...`;
  return `
    <div class="settings-section">
      <div class="settings-section-header">${esc(headerLabel)}</div>
      <div class="settings-task-list">${rows}</div>
      <div class="add-task-row">
        <input type="text" class="new-task-input" placeholder="${esc('New task name...')}" data-section="${esc(section)}" />
        <button class="add-task-btn" data-section="${esc(section)}">Add</button>
      </div>
    </div>`;
}

function renderSettingsContent() {
  if (settingsActiveTab === 'weekly') {
    return WEEKLY_SECTION_ORDER.map((s) => renderSettingsSection(s, s)).join('');
  }
  if (settingsActiveTab === 'monthly') {
    return renderSettingsSection('Monthly', 'Monthly Tasks');
  }
  // annual
  return Array.from({ length: 12 }, (_, i) => {
    const section = `Annual ${i + 1}`;
    const label = MONTH_NAMES[i];
    return renderSettingsSection(section, label);
  }).join('');
}

function renderSettings() {
  settingsPanel.innerHTML = `
    <div class="settings-inner">
      <div class="settings-header">
        <h3>Task Settings</h3>
        <button id="settings-close-btn" class="secondary">Close</button>
      </div>
      <div class="settings-tabs">
        <button class="settings-tab${settingsActiveTab === 'weekly' ? ' active' : ''}" data-tab="weekly">Weekly</button>
        <button class="settings-tab${settingsActiveTab === 'monthly' ? ' active' : ''}" data-tab="monthly">Monthly</button>
        <button class="settings-tab${settingsActiveTab === 'annual' ? ' active' : ''}" data-tab="annual">Annual</button>
      </div>
      <div class="settings-content">${renderSettingsContent()}</div>
      <p class="settings-msg" id="settings-msg"></p>
    </div>`;
}

function settingsMsg(text) {
  const el = document.getElementById('settings-msg');
  if (el) el.textContent = text;
}

async function settingsAddTask(section) {
  const input = settingsPanel.querySelector(`.new-task-input[data-section="${CSS.escape(section)}"]`);
  if (!(input instanceof HTMLInputElement)) return;
  const label = input.value.trim();
  if (!label) { settingsMsg('Please enter a task name.'); return; }
  try {
    const newTask = await api('/api/tasks', { method: 'POST', body: JSON.stringify({ section, label }) });
    tasks.push(newTask);
    input.value = '';
    renderSettings();
    renderWeekly(); renderMonthly(); renderAnnual();
  } catch (err) {
    settingsMsg(err.message);
  }
}

async function settingsDeleteTask(taskId) {
  if (!confirm('Delete this task? All completion history for it will also be removed.')) return;
  try {
    await api(`/api/tasks/${taskId}`, { method: 'DELETE' });
    tasks = tasks.filter((t) => t.id !== taskId);
    delete completions[taskId];
    renderSettings();
    renderWeekly(); renderMonthly(); renderAnnual();
  } catch (err) {
    settingsMsg(err.message);
  }
}

async function settingsMoveTask(taskId, direction) {
  const task = tasks.find((t) => t.id === taskId);
  if (!task) return;
  const sectionTasks = tasks.filter((t) => t.section === task.section).sort((a, b) => a.sort_order - b.sort_order);
  const idx = sectionTasks.findIndex((t) => t.id === taskId);
  const swapIdx = direction === 'up' ? idx - 1 : idx + 1;
  if (swapIdx < 0 || swapIdx >= sectionTasks.length) return;
  const other = sectionTasks[swapIdx];
  const updates = [
    { id: task.id, sort_order: other.sort_order },
    { id: other.id, sort_order: task.sort_order }
  ];
  try {
    await api('/api/tasks/reorder', { method: 'POST', body: JSON.stringify({ items: updates }) });
    const taskObj = tasks.find((t) => t.id === task.id);
    const otherObj = tasks.find((t) => t.id === other.id);
    const tmp = taskObj.sort_order;
    taskObj.sort_order = otherObj.sort_order;
    otherObj.sort_order = tmp;
    renderSettings();
    renderWeekly(); renderMonthly(); renderAnnual();
  } catch (err) {
    settingsMsg(err.message);
  }
}

async function settingsSaveLabel(taskId, newLabel) {
  const task = tasks.find((t) => t.id === taskId);
  if (!task || !newLabel || newLabel === task.label) return;
  try {
    await api(`/api/tasks/${taskId}`, { method: 'PUT', body: JSON.stringify({ label: newLabel, section: task.section }) });
    task.label = newLabel;
    renderWeekly(); renderMonthly(); renderAnnual();
  } catch (err) {
    settingsMsg(err.message);
    // Revert input
    const input = settingsPanel.querySelector(`.settings-task-row[data-task-id="${taskId}"] .task-label-input`);
    if (input instanceof HTMLInputElement) input.value = task.label;
  }
}

async function settingsChangeSection(taskId, newSection) {
  const task = tasks.find((t) => t.id === taskId);
  if (!task || newSection === task.section) return;
  try {
    await api(`/api/tasks/${taskId}`, { method: 'PUT', body: JSON.stringify({ label: task.label, section: newSection }) });
    // Reload tasks to get updated sort_orders
    tasks = (await api('/api/tasks')).tasks;
    renderSettings();
    renderWeekly(); renderMonthly(); renderAnnual();
  } catch (err) {
    settingsMsg(err.message);
    const sel = settingsPanel.querySelector(`.settings-task-row[data-task-id="${taskId}"] .task-section-select`);
    if (sel instanceof HTMLSelectElement) sel.value = task.section;
  }
}

settingsPanel.addEventListener('click', async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;

  if (target.id === 'settings-close-btn') {
    settingsPanel.classList.add('hidden');
    return;
  }

  if (target.classList.contains('settings-tab') && target.dataset.tab) {
    settingsActiveTab = target.dataset.tab;
    renderSettings();
    return;
  }

  if (target.classList.contains('add-task-btn') && target.dataset.section) {
    await settingsAddTask(target.dataset.section);
    return;
  }

  if (target.classList.contains('delete-task-btn')) {
    const row = target.closest('.settings-task-row');
    if (row) await settingsDeleteTask(Number(row.dataset.taskId));
    return;
  }

  if (target.classList.contains('move-up')) {
    const row = target.closest('.settings-task-row');
    if (row) await settingsMoveTask(Number(row.dataset.taskId), 'up');
    return;
  }

  if (target.classList.contains('move-down')) {
    const row = target.closest('.settings-task-row');
    if (row) await settingsMoveTask(Number(row.dataset.taskId), 'down');
    return;
  }
});

settingsPanel.addEventListener('keydown', (event) => {
  if (event.key !== 'Enter') return;
  const target = event.target;
  if (target instanceof HTMLInputElement && target.classList.contains('new-task-input') && target.dataset.section) {
    settingsAddTask(target.dataset.section);
  }
  if (target instanceof HTMLInputElement && target.classList.contains('task-label-input')) {
    target.blur();
  }
});

settingsPanel.addEventListener('focusout', async (event) => {
  const input = event.target;
  if (!(input instanceof HTMLInputElement) || !input.classList.contains('task-label-input')) return;
  const row = input.closest('.settings-task-row');
  if (!row) return;
  await settingsSaveLabel(Number(row.dataset.taskId), input.value.trim());
});

settingsPanel.addEventListener('change', async (event) => {
  const select = event.target;
  if (!(select instanceof HTMLSelectElement) || !select.classList.contains('task-section-select')) return;
  const row = select.closest('.settings-task-row');
  if (!row) return;
  await settingsChangeSection(Number(row.dataset.taskId), select.value);
});

document.getElementById('settings-btn').addEventListener('click', () => {
  settingsPanel.classList.toggle('hidden');
  if (!settingsPanel.classList.contains('hidden')) {
    renderSettings();
  }
});

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

const menuBtn = document.getElementById('menu-btn');
const menuPanel = document.getElementById('menu-panel');

menuBtn.addEventListener('click', (e) => {
  e.stopPropagation();
  menuPanel.classList.toggle('hidden');
});

document.addEventListener('click', () => {
  menuPanel.classList.add('hidden');
});

bootstrap().catch((error) => {
  authMessageEl().textContent = error.message;
});
