'use strict';
let csrf = '';
let discoveryData = null;
let discoveryEnabled = false;
const discoverySelected = new Set();
let usedPhotos = new Set();
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
let mappingDrafts = new Map();
function card(item) {
  const card = el('section', null, 'card body');
  card.append(el('h3', item.name || 'Choose a restaurant'), el('p', item.visit_date));
  if (item.match_note) card.append(el('p', item.match_note, 'notice'));
  if (item.legacy_record) card.append(el('p', 'An old local Added/Skip record exists. Check Beli before repeating any action.', 'notice'));
  const draft = mappingDrafts.get(item.visit_id);
  const include = checkbox('Include this visit in the batch');
  include.input.checked = Boolean(draft?.include); card.append(include.label);
  const select = el('select'); select.setAttribute('aria-label', 'Restaurant and branch');
  const empty = el('option', 'Choose the correct name and address'); empty.value = ''; select.append(empty);
  for (const c of item.candidates) {
    const distance = Number.isFinite(c.distance_m) ? ` (${Math.round(c.distance_m)} m from photos)` : '';
    const option = el('option', c.name + ' — ' + c.address + distance); option.value = c.place_id; select.append(option);
  }
  if (!item.candidates.length) { include.input.disabled = true; card.append(el('p', 'No match. Leave pending and check this visit manually.')); }
  if (draft?.provider && item.candidates.some(c => c.place_id === draft.provider)) select.value = draft.provider;
  card.append(select);
  card.append(el('p', `${item.photos.length} photos in this group — all shown below.`));
  const photos = new Map();
  for (const ref of item.photos) {
    const box = el('div', null, 'photo'); const choice = checkbox('Approve this photo');
    choice.input.checked = draft ? draft.photos.has(ref) : discoveryEnabled;
    box.append(image(ref), choice.label); card.append(box); photos.set(ref, choice.input);
  }
  const noPhotos = checkbox('Continue without photos for this visit'); noPhotos.input.checked = Boolean(draft?.noPhotos); card.append(noPhotos.label);
  if (discoveryEnabled) {
    const tools = el('div', null, 'group-tools');
    const label = el('label', 'Wrong suggestions? Search restaurant name, city or address');
    const query = el('input'); query.type = 'text'; query.maxLength = 200; label.append(query);
    const search = button('Search this visit by name', async () => {
      if (!query.value.trim()) throw new Error('Enter a restaurant name with its city or address.');
      await api('/api/discovery-match', {photos:item.photos, query:query.value.trim()});
    });
    query.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); search.click(); } });
    tools.append(label, search, button('Return group to photo selection', () => api('/api/remove-match', {visit_id:item.visit_id})));
    card.append(tools);
  }
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
  const q = await api('/api/queue');
  mappingDrafts = new Map([...selections].map(([id, s]) => [id, {include:s.include.checked, provider:s.select.value, photos:new Set([...s.photos].filter(([,input]) => input.checked).map(([ref]) => ref)), noPhotos:s.noPhotos.checked}]));
  selections.clear();
  discoveryEnabled = Boolean(q.discovery_enabled);
  $('discovery').hidden = !discoveryEnabled;
  usedPhotos = new Set(q.visits.flatMap(v => v.photos));
  if (discoveryEnabled) {
    const first = discoveryData === null;
    discoveryData = await api('/api/discovery');
    if (first && !discoveryData.likely_food) $('photo-filter').value = 'all';
    renderDiscovery();
  }
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
function renderDiscovery() {
  if (!discoveryData) return;
  const d = discoveryData;
  $('discovery-stats').textContent = `${d.since} through ${d.until}: ${d.photos.length} images, ${d.likely_food} with food labels, ${d.without_gps} without GPS. All are available in these filters; the trial limit applies to visits, not photo discovery.`;
  const mode = $('photo-filter').value;
  const filtered = d.photos.filter(a => mode === 'all' || (mode === 'food' && a.likely_food) ||
    (mode === 'other' && !a.likely_food) || (mode === 'no-gps' && !a.has_location));
  const nodes = filtered.map(a => {
    const box = el('article', null, 'asset');
    const date = new Date(a.taken).toLocaleString();
    const choice = checkbox('Select photo taken ' + date);
    choice.input.checked = discoverySelected.has(a.id);
    choice.input.disabled = usedPhotos.has(a.id);
    choice.input.addEventListener('change', () => {
      if (choice.input.checked) discoverySelected.add(a.id); else discoverySelected.delete(a.id);
      updateDiscoveryCount(filtered.length);
    });
    box.append(image(a.id), choice.label);
    box.append(el('p', (a.likely_food ? 'Local food label' : 'Unlabelled / other') +
      (a.has_location ? ' · GPS available' : ' · No GPS — name search available'), 'hint'));
    if (a.screenshot) box.append(el('p', 'Screenshot — not suggested as a meal photo', 'hint'));
    if (!a.preview_available) box.append(el('p', 'Preview unavailable. Check this image in Photos.', 'hint'));
    if (usedPhotos.has(a.id)) box.append(el('p', 'Already in a review group', 'hint'));
    return box;
  });
  $('photo-grid').replaceChildren(...nodes);
  if (!nodes.length) $('photo-grid').append(el('p', 'No images in this filter. Try All images.'));
  updateDiscoveryCount(filtered.length);
}
function updateDiscoveryCount(visible) {
  $('discovery-count').textContent = `${visible} shown · ${discoverySelected.size} selected across filters`;
  $('match-photos').disabled = !discoverySelected.size;
}
$('photo-filter').addEventListener('change', renderDiscovery);
$('clear-discovery').addEventListener('click', () => { discoverySelected.clear(); renderDiscovery(); });
$('match-photos').addEventListener('click', async () => {
  const photos = [...discoverySelected];
  if (!photos.length) return;
  const b = $('match-photos'); b.disabled = true;
  message('Looking up this selected visit with OSM…');
  try {
    await api('/api/discovery-match', {photos, query:$('restaurant-query').value.trim()});
    photos.forEach(id => discoverySelected.delete(id));
    $('restaurant-query').value = '';
    await load(); message('Visit ready for restaurant and photo approval below. Nothing was uploaded.');
  } catch(e) { message(e.message); b.disabled = false; }
});
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
