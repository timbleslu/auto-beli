'use strict';
let csrf = '';
const $ = id => document.getElementById(id);
const el = (tag, text, cls) => {
  const n = document.createElement(tag);
  if (text !== undefined && text !== null) n.textContent = text;
  if (cls) n.className = cls;
  return n;
};
function message(text) { $('message').textContent = text; }
async function api(path, data) {
  const options = data === undefined ? {} : {
    method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
    body: JSON.stringify(data)
  };
  const r = await fetch(path, options);
  const result = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof result.detail === 'string' ? result.detail : `Request failed (${r.status})`);
  return result;
}
function button(label, fn) {
  const b = el('button', label); b.type = 'button';
  b.addEventListener('click', async () => {
    b.disabled = true;
    try { await fn(); message('Saved locally. Beli results are not machine verified.'); await load(); }
    catch (e) { message(e.message); }
    finally { b.disabled = false; }
  }); return b;
}
function image(ref) {
  const img = el('img', null, 'preview');
  img.src = '/api/photo/' + encodeURIComponent(ref);
  img.alt = 'Photo preview — check this against the original in Photos';
  img.loading = 'lazy';
  img.addEventListener('error', () => { img.replaceWith(el('p', 'Preview unavailable — open Photos to check this image.')); });
  return img;
}
function checkbox(text) {
  const label = el('label'); const input = el('input'); input.type = 'checkbox';
  label.append(input, document.createTextNode(' ' + text));
  return {label, input};
}
const selections = new Map();
function card(item) {
  const card = el('section', null, 'card body');
  card.append(el('h3', item.name || 'Choose a restaurant'), el('p', item.visit_date));
  if (item.match_note) card.append(el('p', item.match_note, 'notice'));
  if (item.legacy_record) card.append(el('p', 'An old local Added/Skip record exists. Check Beli before repeating any action.', 'notice'));
  const include = checkbox('Include this visit in the batch'); card.append(include.label);
  const select = el('select'); select.setAttribute('aria-label', 'Restaurant and branch');
  const empty = el('option', 'Choose the correct name and address'); empty.value = ''; select.append(empty);
  for (const c of item.candidates) {
    const option = el('option', c.name + ' — ' + c.address); option.value = c.place_id; select.append(option);
  }
  if (!item.candidates.length) { include.input.disabled = true; card.append(el('p', 'No match. Leave pending and check this visit manually.')); }
  card.append(select);
  const photos = new Map();
  for (const ref of item.photos) {
    const box = el('div', null, 'photo'); const choice = checkbox('Approve this photo');
    box.append(image(ref), choice.label); card.append(box); photos.set(ref, choice.input);
  }
  const noPhotos = checkbox('Continue without photos for this visit'); card.append(noPhotos.label);
  selections.set(item.visit_id, {include:include.input, select, photos, noPhotos:noPhotos.input});
  return card;
}
async function manual(current, action, extra = {}) {
  await api('/api/manual', {visit_id:current.visit_id, action, ...extra});
}
function renderCurrent(session) {
  const root = $('current'); root.replaceChildren(); const current = session.current;
  root.append(el('h2', 'Session: ' + session.status + ' (manual mode)'));
  if (!current) { root.append(el('p', 'No pending approved visits.')); return; }
  root.append(el('h3', current.name), el('p', current.address), el('p', current.visit_date));
  for (const ref of current.photos) root.append(image(ref));
  if (session.status !== 'running') { root.append(el('p', 'Start or resume to continue. No phone actions are running.')); return; }
  root.append(el('p', 'On your iPhone, open Beli and search for this name. Compare the branch address. Make every rating and comparison choice yourself.'));
  root.append(button('Copy restaurant name', () => navigator.clipboard.writeText(current.name)));
  if (!current.beli_identity) root.append(button('I checked this exact name and address in Beli', () => manual(current, 'identity', {name:current.name,address:current.address})));
  else {
    root.append(el('p', 'Ranking: ' + current.ranking));
    if (current.ranking === 'pending') root.append(button('I checked that my ranking saved in Beli', () => manual(current,'ranking')));
    else {
      for (const [ref, status] of Object.entries(current.attachments)) {
        const row = el('div'); row.append(image(ref), el('p', 'Photo: ' + status));
        if (status === 'pending') row.append(button('I checked this photo is saved on this restaurant', () => manual(current,'photo',{photo:ref})));
        root.append(row);
      }
      root.append(button('Done — next restaurant (manual confirmation)', () => manual(current,'finish')));
      if (Object.values(current.attachments).includes('pending')) root.append(button('Finish without remaining photos — next restaurant', async () => {
        if (confirm('Record that you chose to finish without the pending photos?')) await manual(current,'finish_without_photos');
      }));
    }
  }
  root.append(button('Skip this visit (not complete)', () => manual(current,'skip')));
}
async function load() {
  const s = await api('/api/session'); csrf = s.csrf;
  $('login').hidden = true; $('workspace').hidden = false;
  const q = await api('/api/queue'); selections.clear();
  const approved = new Set(s.visits.map(v => v.visit_id));
  $('root').replaceChildren(...q.visits.filter(v => !approved.has(v.visit_id)).map(card));
  $('rescan').hidden = !q.can_rescan;
  const controls = $('controls'); controls.replaceChildren();
  for (const [action,label] of [['start','Start'],['pause','Pause'],['resume','Resume'],['stop','Stop']]) {
    const b = button(label, () => api('/api/control', {action}));
    b.disabled = !({start:['idle','stopped'],pause:['running'],resume:['paused'],stop:['idle','running','paused']}[action].includes(s.status)); controls.append(b);
  }
  renderCurrent(s);
  $('worklist').replaceChildren(...s.visits.map(v => el('p', `${v.name} — ${v.address}: ${v.outcome}; ranking ${v.ranking}; photos ${Object.values(v.attachments).join(', ') || 'none requested'}`)));
}
$('login-form').addEventListener('submit', async e => {
  e.preventDefault();
  try { await api('/api/login', {code:$('code').value}); $('code').value = ''; await load(); message('Connected.'); }
  catch(e) { message(e.message); }
});
$('approval').addEventListener('submit', async e => {
  e.preventDefault(); const mappings = [];
  for (const [visit_id, s] of selections) {
    if (!s.include.checked) continue;
    const photos = [...s.photos].filter(([,input]) => input.checked).map(([ref]) => ref);
    if (!s.select.value || (!photos.length && !s.noPhotos.checked) || (photos.length && s.noPhotos.checked)) {
      message('Choose a restaurant, then approve photos OR choose without photos for each included visit.'); return;
    }
    mappings.push({visit_id,provider_id:s.select.value,photos});
  }
  if (!mappings.length) { message('Select at least one visit.'); return; }
  try { await api('/api/approve', {mappings}); await load(); message('Batch approved and stored on this Mac.'); }
  catch(e) { message(e.message); }
});
$('rescan').addEventListener('click', async () => {
  try { await api('/api/rescan', {}); await load(); } catch(e) { message(e.message); }
});
$('logout').addEventListener('click', async () => {
  try { await api('/api/logout', {}); location.reload(); } catch(e) { message(e.message); }
});
load().catch(() => { $('login').hidden = false; $('workspace').hidden = true; });
