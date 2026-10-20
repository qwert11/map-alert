'use strict';

// ---------- справочники ----------
const TYPES = {
  ballistic:       { name: 'Баллистические ракеты', short: 'Баллистика', missile: true },
  aeroballistic:   { name: 'Кинжал (аэробаллистика)', short: 'Кинжал', missile: true },
  cruise:          { name: 'Крылатые ракеты', short: 'Крылатые', missile: true },
  supersonic:      { name: 'Циркон / Оникс / Х-22', short: 'Циркон/Оникс', missile: true },
  unknown_missile: { name: 'Ракеты (тип неясен)', short: 'Ракета', missile: true },
  loitering:       { name: 'Бандероль (баражирующий боеприпас)', short: 'Бандероль', missile: false, solid: true },
  jet_drone:       { name: 'Реактивные шахеды', short: 'Реактивные', missile: false },
  shahed:          { name: 'Шахеды и имитаторы', short: 'Шахеды', missile: false },
};
const ROOT_CSS = getComputedStyle(document.documentElement);
const COLOR = t => (ROOT_CSS.getPropertyValue('--' + t) || '').trim() || '#c7ccd4';
const KIND = { hit: 'Попадание', debris: 'Падение обломков', explosions: 'Взрывы (по мониторам)' };
const TK = { energy: 'энергетика', residential: 'жильё', infrastructure: 'инфраструктура', industry: 'промышленность',
  transport: 'транспорт', civil: 'гражданский объект' };
const END = { hit: 'прилёт/взрывы у цели', downed: 'сбит', lost: 'пропал с радаров', unknown: 'итог неизвестен' };
// минут от пуска до первой точки, если время пуска неизвестно
const LEAD = { ballistic: 5, aeroballistic: 6, cruise: 70, supersonic: 15, unknown_missile: 15, loitering: 40, shahed: 150, jet_drone: 45 };
const WD = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];
const MON = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
const PERMANENT = new Set(['Луганська область', 'Автономна Республіка Крим', 'Севастополь']);

const S = {
  mode: 'night', night: null, data: null, index: [], alerts: null, geo: null,
  T: 1440, all: true, playing: false, speed: 3, sel: null,
  layers: { alerts: true, missiles: true, drones: true, impacts: true },
  cache: {}, nightAlerts: null, tracks: [], impacts: [],
};

// ---------- утилиты ----------
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const dayNum = iso => { const [y, m, d] = iso.slice(0, 10).split('-').map(Number); return Date.UTC(y, m - 1, d) / 864e5; };
function lastSunday(y, m) { const d = new Date(Date.UTC(y, m, 0, 1)); d.setUTCDate(d.getUTCDate() - d.getUTCDay()); return d.getTime(); }
function kyivOffset(utcMs) { const y = new Date(utcMs).getUTCFullYear(); return utcMs >= lastSunday(y, 3) && utcMs < lastSunday(y, 10) ? 3 : 2; }
// минуты от начала окна ночи (12:00 накануне по Киеву) для киевского времени "YYYY-MM-DDTHH:MM"
function winMin(night, t) {
  if (!t || t.length < 16) return null;
  const hh = +t.slice(11, 13), mm = +t.slice(14, 16);
  if (Number.isNaN(hh) || Number.isNaN(mm)) return null;
  return (dayNum(t) - dayNum(night) + 1) * 1440 + hh * 60 + mm - 720;
}
function winStartUtc(night) {
  const local = (dayNum(night) - 1) * 864e5 + 12 * 3600e3;
  return local - kyivOffset(local - 3 * 3600e3) * 3600e3;
}
const fmtMin = m => { const x = ((Math.round(m) + 720) % 1440 + 1440) % 1440; return String(Math.floor(x / 60)).padStart(2, '0') + ':' + String(x % 60).padStart(2, '0'); };
const fmtDur = m => { m = Math.round(m); const h = Math.floor(m / 60); return h ? `${h} ч ${m % 60} мин` : `${m} мин`; };
const nightLabel = n => { const d = new Date(dayNum(n) * 864e5); return `${d.getUTCDate()} ${MON[d.getUTCMonth()]}`; };
const nightWd = n => WD[new Date(dayNum(n) * 864e5).getUTCDay()];
const plural = (n, a, b, c) => { const k = n % 10, h = n % 100; return k === 1 && h !== 11 ? a : k >= 2 && k <= 4 && (h < 10 || h >= 20) ? b : c; };
function srcLink(s) {
  if (!s) return '';
  if (/^https?:\/\//.test(s)) { let host = s; try { host = new URL(s).hostname.replace(/^www\./, ''); } catch (e) { /* как есть */ }
    return `<a href="${esc(s)}" target="_blank" rel="noopener">${esc(host)}</a>`; }
  if (/^[\w]+\/\d+$/.test(s)) return `<a href="https://t.me/${esc(s)}" target="_blank" rel="noopener">t.me/${esc(s)}</a>`;
  return esc(s);
}
function union(iv) { // суммарная длина объединения интервалов
  const a = iv.slice().sort((x, y) => x[0] - y[0]); let tot = 0, cs = -1, ce = -1;
  for (const [s, e] of a) { if (s > ce) { if (ce > cs) tot += ce - cs; cs = s; ce = e; } else ce = Math.max(ce, e); }
  if (ce > cs) tot += ce - cs; return tot;
}

// ---------- карта ----------
const map = L.map('map', { zoomControl: true, minZoom: 4, maxZoom: 12, zoomSnap: 0.25, zoomDelta: 0.5, wheelPxPerZoomLevel: 90 }).setView([48.7, 32.5], 6);
// подписи часов на областях: мельче на мелком масштабе, совсем мелкий — без них
const lblScale = () => { const z = map.getZoom(), c = map.getContainer().classList; c.toggle('lbl-sm', z < 5.5); c.toggle('lbl-off', z < 4.6); };
map.on('zoomend', lblScale);
// OSM-тайлы, затемнённые CSS-фильтром (.leaflet-tile-pane): подписи остаются местные, ключ не нужен
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 12, attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
}).addTo(map);
for (const [p, z] of [['obl', 350], ['trk', 420], ['imp', 450], ['lbl', 460], ['hd', 620]]) { map.createPane(p).style.zIndex = z; }
map.getPane('lbl').style.pointerEvents = 'none';
map.getPane('obl').style.mixBlendMode = 'screen';
const gObl = L.layerGroup().addTo(map), gTrk = L.layerGroup().addTo(map), gImp = L.layerGroup().addTo(map), gLbl = L.layerGroup().addTo(map);
let oblLayer = null;

function arrowIcon(color, deg) {
  return L.divIcon({ className: '', iconSize: [14, 14], iconAnchor: [7, 7],
    html: `<svg class="arrow" viewBox="0 0 14 14" style="transform:rotate(${deg}deg);display:block;margin:0"><path d="M2 2 L13 7 L2 12 L5 7 Z" fill="${color}" stroke="#0d1015" stroke-width="1"/></svg>` });
}
function bearing(a, b) { const p = map.project(a, 0), q = map.project(b, 0); return Math.atan2(q.y - p.y, q.x - p.x) * 180 / Math.PI; }

// ---------- тревоги ----------
function nightAlertIntervals(night) {
  const ws = winStartUtc(night) / 1000, res = {}, A = S.alerts;
  for (const [reg, arr] of Object.entries(A.regions)) {
    for (const [s, e] of arr) {
      const a = (A.t0 + s * 60 - ws) / 60, b = (A.t0 + e * 60 - ws) / 60;
      if (b <= 0 || a >= 1440) continue;
      (res[reg] ||= []).push([Math.max(0, a), Math.min(1440, b)]);
    }
  }
  return res;
}
function periodAlertMinutes() {
  const res = {};
  for (const [reg, arr] of Object.entries(S.alerts.regions)) res[reg] = union(arr.map(([s, e]) => [s, e]));
  return res;
}

function styleOblasts() {
  if (!oblLayer) return;
  if (S.mode === 'war') return styleWar();
  gLbl.clearLayers();
  const on = S.layers.alerts;
  let val, max, active = null;
  if (S.mode === 'all') { val = S.periodMin ||= periodAlertMinutes(); max = Math.max(...Object.values(val), 1); }
  else if (S.nightAlerts) {
    if (S.all) { val = {}; for (const [r, iv] of Object.entries(S.nightAlerts)) val[r] = union(iv); max = 720; }
    else { active = new Set(); for (const [r, iv] of Object.entries(S.nightAlerts)) if (iv.some(([a, b]) => a <= S.T && S.T < b)) active.add(r); }
  }
  oblLayer.eachLayer(l => {
    const nm = l.feature.properties.name;
    let fo = 0;
    if (on && !PERMANENT.has(nm)) {
      if (active) fo = active.has(nm) ? 0.5 : (S.nightAlerts[nm] || []).some(([a]) => a <= S.T) ? 0.07 : 0;
      else if (val) fo = val[nm] ? 0.06 + 0.5 * Math.min(1, val[nm] / max) : 0;
    }
    l.setStyle({ fillColor: COLOR('alert'), fillOpacity: fo, color: '#56606e', weight: 0.8, opacity: 0.7, dashArray: null });
  });
  const cnt = active ? active.size : null;
  $('#tl-alerts').textContent = cnt === null ? '' : cnt ? `тревога в ${cnt} ${plural(cnt, 'области', 'областях', 'областях')}` : 'тревог нет';
}
function oblTooltip(l) {
  const nm = l.feature.properties.name;
  if (S.mode === 'war') return warTooltip(nm);
  if (PERMANENT.has(nm)) return `<b>${esc(nm)}</b><br><span class="muted">постоянная тревога</span>`;
  if (S.mode === 'all') { const m = (S.periodMin || {})[nm] || 0; return `<b>${esc(nm)}</b><br>тревога ${fmtDur(m)} за период`; }
  const iv = (S.nightAlerts || {})[nm] || [];
  if (!iv.length) return `<b>${esc(nm)}</b><br><span class="muted">тревог за ночь не было</span>`;
  const list = iv.slice(0, 6).map(([a, b]) => `${fmtMin(a)}–${fmtMin(b)}`).join(', ');
  return `<b>${esc(nm)}</b><br>тревога ${fmtDur(union(iv))} за ночь<br><span class="muted">${list}${iv.length > 6 ? '…' : ''}</span>`;
}

// ---------- треки ----------
function prepTrack(t, night) {
  const pts = (t.launch ? [{ ...t.launch, launch: true }] : []).concat(t.pts);
  let times = pts.map(p => (p.launch ? null : winMin(night, p.t)));
  const known = times.map((v, i) => [v, i]).filter(([v]) => v !== null);
  if (known.length) {
    // заполнить пропуски: внутри — интерполяцией, до первой известной — минус LEAD, после последней — +10 мин на точку
    const [f0, i0] = known[0];
    for (let i = i0 - 1; i >= 0; i--) times[i] = f0 - (pts[i].launch ? LEAD[t.type] || 30 : (i0 - i) * 10);
    for (let k = 0; k < known.length - 1; k++) {
      const [a, ia] = known[k], [b, ib] = known[k + 1];
      for (let i = ia + 1; i < ib; i++) times[i] = a + (b - a) * (i - ia) / (ib - ia);
    }
    const [l0, il] = known[known.length - 1];
    for (let i = il + 1; i < pts.length; i++) times[i] = l0 + (i - il) * 10;
    for (let i = 1; i < times.length; i++) if (times[i] < times[i - 1]) times[i] = times[i - 1];
  } else times = null;
  return { t, pts, ll: pts.map(p => [p.lat, p.lon]), times };
}

function buildTracks() {
  gTrk.clearLayers(); S.tracks = [];
  if (!S.data) return;
  for (const t of S.data.tracks) {
    const o = prepTrack(t, S.night), col = COLOR(t.type), missile = TYPES[t.type]?.missile;
    o.color = col; o.missile = missile;
    o.line = L.polyline(o.ll, { pane: 'trk', color: col, weight: missile ? 2.6 : 1.6, opacity: 0.95,
      dashArray: missile || TYPES[t.type]?.solid ? null : '5 5', lineCap: 'round', lineJoin: 'round' });
    o.hit = L.polyline(o.ll, { pane: 'trk', color: '#000', weight: 14, opacity: 0 }); // широкая невидимая зона клика
    o.arrow = L.marker(o.ll[o.ll.length - 1], { pane: 'trk', interactive: false, icon: arrowIcon(col, 0) });
    o.launchMk = t.launch ? L.circleMarker(o.ll[0], { pane: 'trk', radius: 4, color: col, weight: 1.5, fillOpacity: 0, interactive: false }) : null;
    o.head = L.marker(o.ll[0], { pane: 'hd', interactive: false,
      icon: L.divIcon({ className: '', iconSize: [12, 12], html: `<div class="head" style="color:${col}"></div>` }) });
    const tip = trackTip(o);
    for (const l of [o.hit, o.line]) {
      l.bindTooltip(tip, { sticky: true, direction: 'top', opacity: 1 });
      l.on('click', e => { L.DomEvent.stop(e); selectTrack(o); });
    }
    S.tracks.push(o);
  }
}
function routeText(o) {
  const names = o.pts.map(p => p.n).filter(Boolean);
  if (names.length <= 3) return names.join(' → ');
  return `${names[0]} → … → ${names[names.length - 1]}`;
}
function trackTip(o) {
  const t = o.t, ty = TYPES[t.type];
  const tm = o.times ? `${fmtMin(o.times[o.t.launch ? 1 : 0] ?? o.times[0])}–${fmtMin(o.times[o.times.length - 1])}` : '';
  return `<b style="color:${o.color}">${esc(t.label || ty.short)}${t.count ? ' ×' + t.count : ''}</b> ${tm ? '· ' + tm : ''}<br>${esc(routeText(o))}`;
}
function trackPopup(o) {
  const t = o.t, ty = TYPES[t.type];
  const rows = o.pts.map((p, i) => `<li>${o.times && !p.launch ? `<b>${fmtMin(o.times[i])}</b> ` : ''}${esc(p.n || '')}${p.launch ? ' <span class="muted">(район пуска)</span>' : ''}${p.note ? ` — <span class="muted">${esc(p.note)}</span>` : ''}${p.src ? ' ' + srcLink(p.src) : ''}</li>`).join('');
  return `<h3 style="color:${o.color}">${esc(ty.name)}${t.label && t.label !== ty.short ? ' · ' + esc(t.label) : ''}${t.count ? ' ×' + t.count : ''}</h3>
    <ol>${rows}</ol><div>Итог: ${esc(END[t.end] || t.end)}</div>${t.note ? `<div class="muted">${esc(t.note)}</div>` : ''}`;
}

function layerOn(o) { return o.missile ? S.layers.missiles : S.layers.drones; }

function drawTracks() {
  const T = S.T;
  for (const o of S.tracks) {
    const vis = layerOn(o);
    let ll = o.ll, head = null, state = 'full';
    if (vis && !S.all && o.times) {
      const ts = o.times;
      if (T < ts[0]) state = 'hidden';
      else if (T >= ts[ts.length - 1]) state = T - ts[ts.length - 1] < 25 ? 'arrived' : 'past';
      else {
        let i = 0; while (i < ts.length - 1 && ts[i + 1] <= T) i++;
        const a = o.ll[i], b = o.ll[i + 1], f = ts[i + 1] > ts[i] ? (T - ts[i]) / (ts[i + 1] - ts[i]) : 1;
        head = [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f];
        ll = o.ll.slice(0, i + 1).concat([head]); state = 'moving';
      }
    }
    const show = vis && state !== 'hidden';
    const dim = S.sel && S.sel !== o;
    toggle(gTrk, o.line, show); toggle(gTrk, o.hit, show); toggle(gTrk, o.launchMk, show && !!o.launchMk);
    toggle(gTrk, o.arrow, show && state !== 'moving' && ll.length > 1);
    toggle(gTrk, o.head, show && state === 'moving');
    if (!show) continue;
    o.line.setLatLngs(ll); o.hit.setLatLngs(ll);
    const op = dim ? 0.18 : state === 'past' ? 0.45 : 0.95;
    o.line.setStyle({ opacity: op, weight: (o.missile ? 2.6 : 1.6) + (S.sel === o ? 1.6 : 0) });
    if (o.launchMk) o.launchMk.setStyle({ opacity: op });
    if (head) o.head.setLatLng(head);
    if (ll.length > 1 && state !== 'moving') {
      o.arrow.setLatLng(ll[ll.length - 1]);
      o.arrow.setIcon(arrowIcon(o.color, bearing(ll[ll.length - 2], ll[ll.length - 1])));
      o.arrow.setOpacity(op);
    }
  }
}
function toggle(g, l, on) { if (!l) return; if (on && !g.hasLayer(l)) g.addLayer(l); else if (!on && g.hasLayer(l)) g.removeLayer(l); }

function selectTrack(o) {
  S.sel = S.sel === o ? null : o;
  drawTracks();
  document.querySelectorAll('#trk-list li').forEach(li => li.classList.toggle('on', S.sel && +li.dataset.i === S.tracks.indexOf(S.sel)));
  if (S.sel) {
    map.fitBounds(L.latLngBounds(o.ll).pad(0.25), { maxZoom: 8 });
    L.popup({ maxWidth: 340 }).setLatLng(o.ll[o.ll.length - 1]).setContent(trackPopup(o)).openOn(map);
  } else map.closePopup();
}
map.on('click', () => { if (S.sel) { S.sel = null; drawTracks(); document.querySelectorAll('#trk-list li.on').forEach(li => li.classList.remove('on')); } });

// ---------- прилёты ----------
function impactStyle(m, fresh) {
  const col = m.weapon ? COLOR(m.weapon) : COLOR('alert');
  if (m.kind === 'hit') return { pane: 'imp', radius: 7, color: '#fff', weight: 1.5, fillColor: col, fillOpacity: 0.95, className: fresh ? 'boom' : '' };
  if (m.kind === 'debris') return { pane: 'imp', radius: 5.5, color: col, weight: 2, fillColor: col, fillOpacity: 0.15, dashArray: '2 2' };
  return { pane: 'imp', radius: 4.5, color: col, weight: 1, fillColor: col, fillOpacity: 0.5 };
}
function impactPopup(m) {
  return `<h3>${esc(m.n || '')}${m.dist ? ', ' + esc(m.dist) : ''}</h3>
    <div class="muted">${esc(m.o || '')}${m.t ? ' · ' + esc(m.t.slice(11, 16)) : ''} · ${esc(KIND[m.kind] || m.kind)}${m.weapon ? ' · ' + esc(TYPES[m.weapon]?.short || m.weapon) : ''}${m.tk && TK[m.tk] ? ' · ' + TK[m.tk] : ''}</div>
    ${m.what ? `<p style="margin:6px 0">${esc(m.what)}</p>` : ''}${m.cas ? `<div><b>Пострадавшие:</b> ${esc(m.cas)}</div>` : ''}
    ${m.src ? `<div class="muted" style="margin-top:4px">Источник: ${srcLink(m.src)}</div>` : ''}`;
}
function buildImpacts() {
  gImp.clearLayers(); S.impacts = [];
  if (!S.data) return;
  for (const m of S.data.impacts) {
    const mk = L.circleMarker([m.lat, m.lon], impactStyle(m)).bindPopup(impactPopup(m), { maxWidth: 320 })
      .bindTooltip(`${esc(m.n || '')}${m.dist ? ', ' + esc(m.dist) : ''} · ${esc(KIND[m.kind])}`, { direction: 'top' });
    S.impacts.push({ m, mk, tm: winMin(S.night, m.t) });
  }
}
function drawImpacts() {
  for (const o of S.impacts) {
    const show = S.layers.impacts && (S.all || (o.tm === null ? S.T >= 1440 : o.tm <= S.T));
    toggle(gImp, o.mk, show);
  }
}

// ---------- обзор периода ----------
function buildOverview() {
  gTrk.clearLayers(); gImp.clearLayers(); S.tracks = []; S.impacts = [];
  for (const n of S.index) {
    if (S.layers.missiles) for (const [ty, ll] of n.mt) if (ll.length > 1)
      gTrk.addLayer(L.polyline(ll, { pane: 'trk', color: COLOR(ty), weight: 1.4, opacity: 0.28, interactive: false }));
    if (S.layers.impacts) for (const [lat, lon, kind, w, name] of n.imp) {
      const col = w ? COLOR(w) : COLOR('alert');
      gImp.addLayer(L.circleMarker([lat, lon], { pane: 'imp', radius: kind === 'hit' ? 4.5 : 3, color: col, weight: kind === 'hit' ? 0 : 1,
        fillColor: col, fillOpacity: kind === 'hit' ? 0.75 : 0.25 })
        .bindTooltip(`${esc(name || '')} · ${nightLabel(n.night)}`, { direction: 'top' })
        .on('click', () => go(n.night)));
    }
  }
}

// ---------- панель ----------
function renderNightList() {
  const ol = $('#nights');
  $('#nights-count').textContent = S.index.length;
  ol.innerHTML = S.index.slice().reverse().map(n => {
    const c = n.c || {}, pips = [1, 2, 3, 4].map(i => `<i class="${(n.intensity || 0) >= i ? 'on' : ''}"></i>`).join('');
    return `<li data-n="${n.night}" class="${S.mode === 'night' && n.night === S.night ? 'on' : ''}">
      <div class="n-date"><b>${nightLabel(n.night).split(' ')[0]}</b><span>${nightLabel(n.night).split(' ')[1]}, ${nightWd(n.night)}</span></div>
      <div class="n-head">${esc(n.headline || 'без происшествий')}</div>
      <div class="n-meta"><span class="pips" title="интенсивность">${pips}</span>
        ${c.missiles ? `<span class="chip"><span class="dot" style="background:${COLOR('cruise')}"></span>${c.est_m ? '≈' : ''}${c.missiles} ${plural(c.missiles, 'ракета', 'ракеты', 'ракет')}</span>` : ''}
        ${c.drones ? `<span class="chip"><span class="dot" style="background:${COLOR('shahed')}"></span>${c.drones} дронов</span>` : ''}
        ${n.nImpacts ? `<span class="chip"><span class="dot" style="background:#fff"></span>${n.nImpacts} ${plural(n.nImpacts, 'прилёт', 'прилёта', 'прилётов')}</span>` : ''}
      </div></li>`;
  }).join('');
}
$('#nights').addEventListener('click', e => { const li = e.target.closest('li[data-n]'); if (li) go(li.dataset.n); });

function afTable(af) {
  if (!af || !(af.launched || []).length) return '';
  const down = {}; for (const x of af.downed || []) down[x.type] = (down[x.type] || 0) + (x.count || x.count_est || 0);
  const rows = af.launched.map(x => `<tr><td><span class="dot" style="background:${COLOR(x.type)}"></span> ${esc(x.label || TYPES[x.type]?.short || x.type)}${x.from ? `<br><small class="muted">${esc(x.from)}</small>` : ''}</td>
      <td class="n">${x.count ?? (x.count_est ? '≈' + x.count_est : '—')}</td><td class="n">${down[x.type] || '—'}</td></tr>`).join('');
  return `<table class="af"><thead><tr><th>Чем атаковали (Повітряні сили)</th><th class="n">запущено</th><th class="n">сбито</th></tr></thead><tbody>${rows}</tbody></table>
    <p class="af-text">${af.hits_locations != null ? `Попадания на ${af.hits_locations} ${plural(af.hits_locations, 'локации', 'локациях', 'локациях')}. ` : ''}${af.debris_locations != null ? `Обломки — на ${af.debris_locations}. ` : ''}${af.period ? esc(af.period) + '. ' : ''}${af.src ? srcLink(af.src) : ''}</p>`;
}

function renderNightDetail() {
  const d = S.data, n = S.index.find(x => x.night === S.night) || {};
  if (!d) { $('#detail').innerHTML = '<p class="muted">Загрузка…</p>'; return; }
  const c = n.c || {};
  const byType = {};
  S.tracks.forEach((o, i) => (byType[o.t.type] ||= []).push([o, i]));
  const trk = Object.keys(TYPES).filter(t => byType[t]).map(t => byType[t].map(([o, i]) =>
    `<li data-i="${i}"><span class="dot" style="background:${o.color}"></span><div>${esc(o.t.label || TYPES[t].short)}${o.t.count ? ' ×' + o.t.count : ''}
      ${o.times ? `<span class="muted"> · ${fmtMin(o.times[o.t.launch ? 1 : 0] ?? o.times[0])}</span>` : ''}<small>${esc(routeText(o))}</small></div></li>`).join('')).join('');
  const imp = S.impacts.slice().sort((a, b) => (a.tm ?? 9e9) - (b.tm ?? 9e9)).map((o, i) => {
    const m = o.m;
    return `<li data-k="${S.impacts.indexOf(o)}"><span class="dot" style="background:${m.kind === 'hit' ? '#fff' : m.weapon ? COLOR(m.weapon) : COLOR('alert')}"></span><div>${esc(m.n || '')}${m.dist ? ', ' + esc(m.dist) : ''}
      <span class="muted">· ${m.t ? esc(m.t.slice(11, 16)) + ' · ' : ''}${esc(KIND[m.kind])}</span><small>${esc(m.what || '')}${m.cas ? ' · ' + esc(m.cas) : ''}</small></div></li>`;
  }).join('');
  const alertMin = S.nightAlerts ? Object.entries(S.nightAlerts).map(([r, iv]) => [r, union(iv)]).sort((a, b) => b[1] - a[1]) : [];
  $('#detail').innerHTML = `
    <h2>Ночь на ${nightLabel(S.night)}, ${nightWd(S.night)}</h2>
    <div class="muted" style="font-size:12px">с 12:00 ${nightLabel(new Date((dayNum(S.night) - 1) * 864e5).toISOString())} до 12:00 ${nightLabel(S.night)} по Киеву</div>
    <p class="lead">${esc(d.summary || d.headline || '')}</p>
    <div class="kpis">
      <div class="kpi"><b>${c.est_m && c.missiles ? '≈' : ''}${c.missiles || 0}</b><span>ракет${c.from_af ? '' : ' (по трекам)'}</span></div>
      <div class="kpi"><b>${c.est_d && c.drones ? '≈' : ''}${c.drones || 0}</b><span>дронов${c.from_af ? '' : ' (по трекам)'}</span></div>
      <div class="kpi"><b>${alertMin.length}</b><span>${plural(alertMin.length, 'область', 'области', 'областей')} с тревогой</span></div>
    </div>
    ${afTable(d.af)}
    <details class="blk" open><summary>Траектории · ${S.tracks.length}</summary>
      ${S.tracks.length ? `<ul class="items" id="trk-list">${trk}</ul>` : '<p class="note">Треков за ночь не восстановлено.</p>'}</details>
    <details class="blk" ${S.impacts.length ? 'open' : ''}><summary>Прилёты и последствия · ${S.impacts.length}</summary>
      ${S.impacts.length ? `<ul class="items" id="imp-list">${imp}</ul>` : '<p class="note">Сообщений о прилётах не найдено.</p>'}</details>
    <details class="blk"><summary>Тревоги по областям</summary>
      <ul class="top">${alertMin.map(([r, m]) => `<li><span>${esc(r)}</span><span class="muted">${fmtDur(m)}</span></li>`).join('') || '<li>нет</li>'}</ul></details>
    ${d.notes ? `<p class="note">${esc(d.notes)}</p>` : ''}`;
  $('#trk-list')?.addEventListener('click', e => { const li = e.target.closest('li[data-i]'); if (li) selectTrack(S.tracks[+li.dataset.i]); });
  $('#imp-list')?.addEventListener('click', e => {
    const li = e.target.closest('li[data-k]'); if (!li) return;
    const o = S.impacts[+li.dataset.k];
    if (!S.all && o.tm !== null && o.tm > S.T) showAll();
    map.setView([o.m.lat, o.m.lon], Math.max(map.getZoom(), 9)); toggle(gImp, o.mk, true); o.mk.openPopup();
  });
}

function renderOverview() {
  const N = S.index;
  const tot = N.reduce((a, n) => { a.m += n.c?.missiles || 0; a.d += n.c?.drones || 0; a.i += n.nImpacts || 0; return a; }, { m: 0, d: 0, i: 0 });
  const maxV = Math.max(1, ...N.map(n => (n.c?.missiles || 0) * 5 + (n.c?.drones || 0)));
  const bars = N.map(n => {
    const m = n.c?.missiles || 0, d = n.c?.drones || 0;
    return `<div data-n="${n.night}" title="${nightLabel(n.night)}: ${m} ракет, ${d} дронов"><i style="height:${(d / maxV) * 90}px;background:${COLOR('shahed')}"></i><i style="height:${(m * 5 / maxV) * 90}px;background:${COLOR('cruise')}"></i></div>`;
  }).join('');
  const cities = {};
  for (const n of N) for (const [, , kind, , name] of n.imp) if (kind !== 'explosions' && name) cities[name] = (cities[name] || 0) + 1;
  const topC = Object.entries(cities).sort((a, b) => b[1] - a[1]).slice(0, 10);
  const pm = S.periodMin ||= periodAlertMinutes();
  const topA = Object.entries(pm).sort((a, b) => b[1] - a[1]).slice(0, 8);
  $('#detail').innerHTML = `
    <h2>Весь период</h2>
    <div class="muted" style="font-size:12px">${N.length ? `ночи с ${nightLabel(N[0].night)} по ${nightLabel(N[N.length - 1].night)}` : ''}</div>
    <div class="kpis">
      <div class="kpi"><b>${tot.m}</b><span>ракет</span></div>
      <div class="kpi"><b>${tot.d}</b><span>дронов</span></div>
      <div class="kpi"><b>${tot.i}</b><span>прилётов на карте</span></div>
    </div>
    <h2 class="sec">По ночам</h2>
    <div class="bars" id="bars">${bars}</div>
    <div class="bars-axis"><span>${N.length ? nightLabel(N[0].night) : ''}</span><span><span class="dot" style="background:${COLOR('cruise')}"></span> ракеты ×5 &nbsp;<span class="dot" style="background:${COLOR('shahed')}"></span> дроны</span><span>${N.length ? nightLabel(N[N.length - 1].night) : ''}</span></div>
    <h2 class="sec">Чаще всего прилёты</h2>
    <ul class="top">${topC.map(([c, k]) => `<li><span>${esc(c)}</span><span class="muted">${k}</span></li>`).join('') || '<li>нет данных</li>'}</ul>
    <h2 class="sec">Дольше всего под тревогой</h2>
    <ul class="top">${topA.map(([r, m]) => `<li><span>${esc(r)}</span><span class="muted">${Math.round(m / 60)} ч</span></li>`).join('')}</ul>
    <p class="note">Цифры ракет и дронов — из утренних сводок Повітряних сил. Нажмите на столбик или точку, чтобы открыть ночь.</p>`;
  $('#bars').addEventListener('click', e => { const b = e.target.closest('[data-n]'); if (b) go(b.dataset.n); });
}

function renderLegend() {
  if (S.mode === 'war') {
    $('#legend').innerHTML = $('#legend-m').innerHTML = `<span class="lg muted">последний удар:</span>
      ${S.st.years.map(y => `<span class="lg"><span class="dot" style="background:${YEAR_COLOR[y]};width:10px;height:10px"></span>${y}</span>`).join('')}
      <span class="lg"><span class="dot" style="border:1.5px dashed #aaa;width:11px;height:11px"></span>район без точного места</span>
      <span class="lg muted">размер — дней с ударами · клик по карте — проверка радиуса</span>`;
    return;
  }
  const present = new Set();
  if (S.mode === 'all') S.index.forEach(n => n.mt.forEach(([t]) => present.add(t)));
  else S.tracks.forEach(o => present.add(o.t.type));
  const items = Object.keys(TYPES).filter(t => present.has(t)).map(t =>
    `<span class="lg"><span class="ln ${TYPES[t].missile || TYPES[t].solid ? '' : 'dash'}" style="border-color:${COLOR(t)}"></span>${TYPES[t].short}</span>`);
  items.push(`<span class="lg"><span class="dot" style="background:${COLOR('alert')};border:1.5px solid #fff;width:10px;height:10px"></span>попадание</span>`);
  items.push(`<span class="lg"><span class="dot" style="border:1.5px dashed ${COLOR('alert')};width:10px;height:10px"></span>обломки</span>`);
  items.push(`<span class="lg"><span class="dot" style="background:${COLOR('alert')};opacity:.5"></span>тревога</span>`);
  $('#legend').innerHTML = $('#legend-m').innerHTML = items.join('');
}

// ---------- таймлайн ----------
function renderChart() {
  const svg = $('#tl-chart');
  if (!S.nightAlerts) { svg.innerHTML = ''; return; }
  const step = 10, ivs = Object.values(S.nightAlerts);
  let pts = [], mx = 1;
  const vals = [];
  for (let m = 0; m <= 1440; m += step) { const v = ivs.filter(iv => iv.some(([a, b]) => a <= m && m < b)).length; vals.push(v); mx = Math.max(mx, v); }
  vals.forEach((v, i) => pts.push(`${i * step},${22 - (v / mx) * 18}`));
  const ticks = [];
  for (const o of S.tracks) if (o.times) ticks.push(`<rect x="${o.times[o.times.length - 1] - 1}" y="0" width="3" height="5" fill="${o.color}"/>`);
  for (const o of S.impacts) if (o.tm !== null) ticks.push(`<rect x="${o.tm - 1}" y="0" width="3" height="5" fill="#fff"/>`);
  svg.setAttribute('viewBox', '0 0 1440 22');
  svg.innerHTML = `<polygon points="0,22 ${pts.join(' ')} 1440,22" fill="${COLOR('alert')}" fill-opacity=".35"/>${ticks.join('')}`;
}
function setTime(T, all) {
  S.T = Math.max(0, Math.min(1440, T)); S.all = !!all;
  $('#tl-range').value = S.T;
  $('#tl-time').textContent = S.all ? 'вся ночь' : fmtMin(S.T);
  styleOblasts(); drawTracks(); drawImpacts();
}
function showAll() { stop(); setTime(1440, true); }
$('#tl-range').addEventListener('input', e => { stop(); setTime(+e.target.value, false); });
$('#tl-all').addEventListener('click', showAll);
let raf = null, lastTs = 0;
function stop() { S.playing = false; $('#play').textContent = '▶'; if (raf) cancelAnimationFrame(raf); raf = null; }
function firstEvent() {
  let f = 1440;
  for (const o of S.tracks) if (o.times) f = Math.min(f, o.times[0]);
  for (const o of S.impacts) if (o.tm !== null) f = Math.min(f, o.tm);
  return f < 1440 ? Math.max(0, f - 20) : 360;
}
$('#play').addEventListener('click', () => {
  if (S.playing) return stop();
  if (S.all || S.T >= 1439) setTime(firstEvent(), false);
  S.playing = true; $('#play').textContent = '❚❚'; lastTs = performance.now();
  const tick = ts => {
    if (!S.playing) return;
    const dt = Math.min(0.1, (ts - lastTs) / 1000); lastTs = ts;
    const T = S.T + dt * S.speed * 10;
    if (T >= 1440) { setTime(1440, false); stop(); return; }
    setTime(T, false); raf = requestAnimationFrame(tick);
  };
  raf = requestAnimationFrame(tick);
});
document.querySelectorAll('.tl-speed button').forEach(b => b.addEventListener('click', () => {
  S.speed = +b.dataset.speed; document.querySelectorAll('.tl-speed button').forEach(x => x.classList.toggle('on', x === b));
}));


// ---------- прилёты за всю войну по населённым пунктам ----------
const fmtInt = n => Math.round(n).toLocaleString('ru-RU');
const shortOb = n => (n || '').replace(' область', '').replace('Автономна Республіка ', '');
const dateLabel = t => (t ? `${+t.slice(8, 10)} ${MON[+t.slice(5, 7) - 1]} ${t.slice(0, 4)}` : '');
// цвет — последний год, когда в место прилетало: чем свежее, тем горячее
const YEAR_COLOR = { 2022: '#7c8798', 2023: '#38bdf8', 2024: '#facc15', 2025: '#fb923c', 2026: '#ff453a' };
const gStr = L.layerGroup().addTo(map);
S.years = new Set(); S.oblFilter = '';
let radiusLayer = null;

async function loadStrikes() { if (!S.st) S.st = await fetch('data/strikes.json', { cache: 'no-cache' }).then(r => r.json()); return S.st; }
const warYears = () => S.st.years;
const yearOn = y => !S.years.size || S.years.has(y);
function ptStats(p) { // по выбранным годам: дней с ударами, из них с разрушениями, последний год
  let n = 0, h = 0, last = null;
  S.st.years.forEach((y, i) => { if (yearOn(y) && p[4][i]) { n += p[4][i]; h += p[5][i]; last = y; } });
  return { n, h, last };
}
const yearsRow = arr => S.st.years.map((y, i) => `<span style="color:${arr[i] ? YEAR_COLOR[y] : 'var(--faint)'}">${y}: <b>${arr[i] || '—'}</b></span>`).join(' · ');
function strikePopup(p, isRaion) {
  const [dt, tx, url] = p[6];
  return `<h3>${esc(p[2])}</h3><div class="muted">${esc(S.st.oblasts[p[3]] || '')}${isRaion ? ' · удары в районе без точного места' : ''}</div>
    <div style="margin:6px 0">Дней с ударами по годам:<br>${yearsRow(p[4])}</div>
    <div>Из них с разрушениями или жертвами: ${p[5].reduce((a, b) => a + b, 0)}</div>
    <div class="muted" style="margin-top:6px">Последний: ${dateLabel(dt)}${tx ? ` — «${esc(tx)}»` : ''}${url ? ` <a href="${esc(url)}" target="_blank" rel="noopener">источник</a>` : ''}</div>`;
}
function drawStrikes() {
  gStr.clearLayers();
  const items = [];
  for (const p of S.st.p) {
    if (S.oblFilter && S.st.oblasts[p[3]] !== S.oblFilter) continue;
    const s = ptStats(p);
    if (s.n) items.push([p, s]);
  }
  items.sort((a, b) => (a[1].last - b[1].last) || (b[1].n - a[1].n)); // свежие и мелкие — сверху
  for (const [p, s] of items) {
    const col = YEAR_COLOR[s.last];
    L.circleMarker([p[0], p[1]], { pane: 'imp', radius: Math.min(22, 2.5 + 1.5 * Math.sqrt(s.n)), color: col, weight: 1,
      opacity: 0.95, fillColor: col, fillOpacity: s.h ? 0.55 : 0.22 })
      .bindTooltip(`<b>${esc(p[2])}</b> · ${esc(shortOb(S.st.oblasts[p[3]]))}<br>${yearsRow(p[4])}`, { direction: 'top', opacity: 1 })
      .on('click', e => { L.DomEvent.stop(e); L.popup({ maxWidth: 340 }).setLatLng(e.latlng).setContent(strikePopup(p)).openOn(map); })
      .addTo(gStr);
  }
  S.stItems = items;
  // удары, где новости назвали только район: пунктирный круг в центре района
  for (const p of S.st.r || []) {
    if (S.oblFilter && S.st.oblasts[p[3]] !== S.oblFilter) continue;
    const s = ptStats(p);
    if (!s.n) continue;
    const col = YEAR_COLOR[s.last];
    L.circleMarker([p[0], p[1]], { pane: 'imp', radius: Math.min(26, 9 + 2 * Math.sqrt(s.n)), color: col, weight: 1.5,
      dashArray: '3 4', fillColor: col, fillOpacity: 0.05 })
      .bindTooltip(`<b>${esc(p[2])}</b> · удары без точного места<br>${yearsRow(p[4])}`, { direction: 'top', opacity: 1 })
      .on('click', e => { L.DomEvent.stop(e); L.popup({ maxWidth: 340 }).setLatLng(e.latlng).setContent(strikePopup(p, true)).openOn(map); })
      .addTo(gStr);
  }
}
function styleWar() {
  gLbl.clearLayers();
  oblLayer.eachLayer(l => l.setStyle({ fillOpacity: 0, color: '#56606e', weight: 0.8, opacity: 0.7, dashArray: null }));
  drawStrikes();
}
function warTooltip(nm) {
  const k = (S.stItems || []).filter(([p]) => S.st.oblasts[p[3]] === nm).length;
  return `<b>${esc(nm)}</b><br><span class="muted">${k ? `${k} ${plural(k, 'место', 'места', 'мест')} с ударами` : 'ударов в базе нет'}</span>`;
}

// проверка места: сколько ударов было в радиусе 10 и 25 км
const km = (a, b, c, d) => { const t = Math.PI / 180, x = Math.sin((c - a) * t / 2) ** 2 + Math.cos(a * t) * Math.cos(c * t) * Math.sin((d - b) * t / 2) ** 2; return 12742 * Math.asin(Math.sqrt(x)); };
function radiusCheck(ll, label) {
  if (radiusLayer) map.removeLayer(radiusLayer);
  const near = [];
  for (const p of S.st.p) { const d = km(ll.lat, ll.lng, p[0], p[1]); if (d <= 25) near.push([d, p]); }
  near.sort((a, b) => a[0] - b[0]);
  const sum = r => S.st.years.map((y, i) => near.filter(([d]) => d <= r).reduce((t, [, p]) => t + p[4][i], 0));
  radiusLayer = L.layerGroup([
    L.circle(ll, { radius: 10000, color: '#fff', weight: 1.2, dashArray: '4 4', fill: false, interactive: false }),
    L.circle(ll, { radius: 25000, color: '#8b95a4', weight: 1, dashArray: '2 6', fill: false, interactive: false }),
  ]).addTo(map);
  const rnear = (S.st.r || []).map(p => [km(ll.lat, ll.lng, p[0], p[1]), p]).filter(([d]) => d <= 35).sort((a, b) => a[0] - b[0]);
  const rlist = rnear.map(([d, p]) => `<li>${esc(p[2])} (центр в ${d.toFixed(0)} км): ${yearsRow(p[4])}</li>`).join('');
  const list = near.slice(0, 6).map(([d, p]) => `<li>${esc(p[2])} — ${d < 1 ? '<1' : d.toFixed(0)} км, последний удар ${dateLabel(p[6][0])}</li>`).join('');
  L.popup({ maxWidth: 360 }).setLatLng(ll).setContent(`<h3>${esc(label || `${ll.lat.toFixed(3)}, ${ll.lng.toFixed(3)}`)}</h3>
    <div style="margin:4px 0">Дней с ударами в радиусе <b>10 км</b>:<br>${yearsRow(sum(10))}</div>
    <div style="margin:4px 0">в радиусе <b>25 км</b>:<br>${yearsRow(sum(25))}</div>
    ${near.length ? `<div class="muted">Ближайшие места с ударами:</div><ol>${list}</ol>` : '<div>В радиусе 25 км точных мест с ударами в базе нет.</div>'}
    ${rnear.length ? `<div class="muted" style="margin-top:4px">Удары в районе без точного места:</div><ul style="margin:4px 0;padding-left:18px">${rlist}</ul>` : ''}`).openOn(map);
}
map.on('click', e => { if (S.mode === 'war' && S.st) radiusCheck(e.latlng); });

async function findPlace(q) {
  const box = $('#find-res');
  q = q.trim(); if (!q) { box.innerHTML = ''; return; }
  const lq = q.toLowerCase();
  const local = S.st.p.filter(p => p[2].toLowerCase().startsWith(lq)).slice(0, 5)
    .map(p => ({ lat: p[0], lon: p[1], name: p[2], sub: shortOb(S.st.oblasts[p[3]]) }));
  box.innerHTML = '<p class="muted">Ищу…</p>';
  let osm = [];
  try {
    const u = `https://nominatim.openstreetmap.org/search?format=json&limit=6&countrycodes=ua&accept-language=uk&q=${encodeURIComponent(q)}`;
    osm = (await fetch(u).then(r => r.json())).map(r => ({ lat: +r.lat, lon: +r.lon, name: r.display_name.split(',')[0], sub: r.display_name.split(',').slice(1, 3).join(',') }));
  } catch (e) { /* OSM недоступен — останутся только места из базы */ }
  const seen = new Set(), res = [];
  for (const r of local.concat(osm)) { const k = r.name + Math.round(r.lat * 20) + Math.round(r.lon * 20); if (!seen.has(k)) { seen.add(k); res.push(r); } }
  box.innerHTML = res.length ? `<ul class="items">${res.map((r, i) => `<li data-i="${i}"><span class="dot" style="background:var(--muted)"></span><div>${esc(r.name)}<small>${esc(r.sub)}</small></div></li>`).join('')}</ul>`
    : '<p class="muted">Ничего не нашёл.</p>';
  box.querySelector('ul')?.addEventListener('click', e => {
    const li = e.target.closest('li[data-i]'); if (!li) return;
    const r = res[+li.dataset.i], ll = L.latLng(r.lat, r.lon);
    map.setView(ll, 10); radiusCheck(ll, r.name);
  });
}

function setYears(ys) {
  const all = warYears();
  S.years = new Set(ys.filter(y => all.includes(y)));
  if (S.years.size === all.length) S.years.clear();
  history.replaceState(null, '', '#war' + (S.years.size ? '=' + [...S.years].sort().join(',') : ''));
  drawStrikes(); renderWar();
}
function renderWar() {
  const st = S.st, yrs = st.years, items = S.stItems || [];
  const days = items.reduce((t, [, s]) => t + s.n, 0);
  const latestY = [...yrs].reverse().find(yearOn);
  const iL = yrs.indexOf(latestY);
  const inLatest = items.filter(([p]) => p[4][iL]).length;
  const range = S.years.size ? [...S.years].sort().join(', ') : `${yrs[0]}–${yrs[yrs.length - 1]}`;
  const top = items.slice().sort((a, b) => b[1].n - a[1].n).slice(0, 40);
  const maxN = top.length ? top[0][1].n : 1;
  const prev = $('#find-q')?.value || '';
  $('#detail').innerHTML = `
    <h2>Прилёты по городам и сёлам</h2>
    <div class="muted" style="font-size:12px">с 24 фев 2022 по ${dateLabel(st.to)} · по новостям, база VIINA</div>
    <div class="years" role="group" aria-label="Годы">
      <button data-y="all" class="${S.years.size ? '' : 'on'}">Все годы</button>
      ${yrs.map(y => `<button data-y="${y}" class="${S.years.has(y) ? 'on' : ''}" style="${S.years.has(y) ? '' : `border-color:${YEAR_COLOR[y]}55`}">${y}</button>`).join('')}
    </div>
    <form id="find" class="find"><input id="find-q" type="search" placeholder="Проверить место: село, город…" value="${esc(prev)}" autocomplete="off"><button>Найти</button></form>
    <div id="find-res"></div>
    <p class="note" style="margin:6px 0 0">Клик по любому месту на карте — сколько дней с ударами было в радиусе 10 и 25 км, по годам.</p>
    <div class="kpis">
      <div class="kpi"><b>${fmtInt(items.length)}</b><span>мест с ударами · ${range}</span></div>
      <div class="kpi"><b>${fmtInt(days)}</b><span>дней с ударами, сумма по местам</span></div>
      <div class="kpi"><b>${fmtInt(inLatest)}</b><span>мест с ударами в ${latestY}</span></div>
    </div>
    <select id="obl-filter" class="sel"><option value="">Все области</option>${st.oblasts.map(o => `<option ${o === S.oblFilter ? 'selected' : ''}>${esc(o)}</option>`).join('')}</select>
    <h2 class="sec">Чаще всего · ${range}${S.oblFilter ? ' · ' + esc(shortOb(S.oblFilter)) : ''}</h2>
    <ol class="rank" id="rank">${top.map(([p, s], i) => `<li data-i="${st.p.indexOf(p)}"><span class="rk">${i + 1}</span><span class="nm"><span class="dot" style="background:${YEAR_COLOR[s.last]};margin-right:6px"></span>${esc(p[2])}</span><span class="bar"><i style="width:${(s.n / maxN) * 100}%;background:${YEAR_COLOR[s.last]}"></i></span><span class="v">${fmtInt(s.n)} дн</span></li>`).join('') || '<li>нет</li>'}</ol>
    <p class="note">Точка — населённый пункт, где по новостям был удар: ракета, дрон, авиабомба или артиллерия. Цвет — последний год
      с ударом (из выбранных), размер — сколько дней с ударами, заливка гуще — были разрушения или жертвы.
      Источник — <a href="https://github.com/zhukovyuri/VIINA" target="_blank" rel="noopener">VIINA</a> (Мичиганский университет):
      заголовки украинских СМИ, привязанные к месту. Каждый заголовок проверен: в нём есть название места и слово про удар,
      нет другой области; для сёл — названа своя область. Чего не было в новостях, здесь нет: мелкие сёла с одним дроном
      могут не попасть, а крупные города попадают почти каждый день.</p>`;
  document.querySelector('.years').addEventListener('click', e => {
    const b = e.target.closest('button[data-y]'); if (!b) return;
    if (b.dataset.y === 'all') return setYears([]);
    const cur = new Set(S.years); cur.has(b.dataset.y) ? cur.delete(b.dataset.y) : cur.add(b.dataset.y);
    setYears([...cur]);
  });
  $('#find').addEventListener('submit', e => { e.preventDefault(); findPlace($('#find-q').value); });
  $('#obl-filter').addEventListener('change', e => {
    S.oblFilter = e.target.value; drawStrikes(); renderWar();
    if (S.oblFilter) { oblLayer.eachLayer(l => { if (l.feature.properties.name === S.oblFilter) map.fitBounds(l.getBounds(), { paddingTopLeft: [0, 40] }); }); }
  });
  $('#rank').addEventListener('click', e => {
    const li = e.target.closest('li[data-i]'); if (!li) return;
    const p = st.p[+li.dataset.i];
    map.setView([p[0], p[1]], Math.max(map.getZoom(), 9));
    L.popup({ maxWidth: 340 }).setLatLng([p[0], p[1]]).setContent(strikePopup(p)).openOn(map);
  });
}

// ---------- слои, режимы, навигация ----------
document.querySelectorAll('#layers input').forEach(inp => inp.addEventListener('change', () => {
  S.layers[inp.dataset.layer] = inp.checked;
  if (S.mode === 'all') { buildOverview(); styleOblasts(); } else { styleOblasts(); drawTracks(); drawImpacts(); }
}));
document.querySelectorAll('.tabs button').forEach(b => b.addEventListener('click', () => {
  if (b.dataset.mode === 'all') go('all');
  else if (b.dataset.mode === 'war') go('war' + (S.years.size ? '=' + [...S.years].sort().join(',') : ''));
  else go(S.night || S.index[S.index.length - 1]?.night);
}));
$('#sheet-toggle').addEventListener('click', () => {
  const p = $('#panel'); p.classList.toggle('min'); $('#sheet-toggle').textContent = p.classList.contains('min') ? '▴' : '▾';
  setTimeout(() => map.invalidateSize(), 250);
});

function go(target) { if (!target) return; if (location.hash.slice(1) !== target) location.hash = target; else route(); }
window.addEventListener('hashchange', route);

async function loadNight(n) {
  if (!S.cache[n]) S.cache[n] = fetch(`data/nights/${n}.json`, { cache: 'no-cache' }).then(r => r.ok ? r.json() : null).catch(() => null);
  return S.cache[n];
}

async function route() {
  stop(); map.closePopup(); S.sel = null;
  gStr.clearLayers(); if (radiusLayer) { map.removeLayer(radiusLayer); radiusLayer = null; }
  const h = decodeURIComponent(location.hash.slice(1)) || 'war'; // по умолчанию — прилёты за всю войну
  const nights = S.index.map(n => n.night);
  if (h.startsWith('war')) {
    S.mode = 'war'; S.data = null; S.nightAlerts = null;
    $('#timeline').classList.add('off');
    gTrk.clearLayers(); gImp.clearLayers(); S.tracks = []; S.impacts = [];
    document.body.dataset.mode = 'war';
    $('#detail').innerHTML = '<p class="muted">Загрузка базы прилётов…</p>';
    await loadStrikes();
    if (S.mode !== 'war') return; // пока грузилась база, ушли в другой режим
    S.years = new Set((h.split('=')[1] || '').split(',').filter(y => warYears().includes(y)));
    styleWar(); renderWar(); renderLegend();
    map.fitBounds(oblLayer.getBounds(), { paddingTopLeft: [0, 20], paddingBottomRight: [0, 10] });
  } else if (h === 'all') {
    S.mode = 'all'; S.data = null; S.nightAlerts = null;
    $('#timeline').classList.add('off');
    buildOverview(); styleOblasts(); renderOverview(); renderLegend();
  } else {
    const n = nights.includes(h) ? h : nights[nights.length - 1];
    if (!n) return;
    S.mode = 'night'; S.night = n; $('#timeline').classList.remove('off');
    S.data = null; renderNightDetail();
    const d = await loadNight(n);
    if (S.night !== n) return;
    S.data = d || { tracks: [], impacts: [] }; S.nightAlerts = nightAlertIntervals(n);
    buildTracks(); buildImpacts(); setTime(1440, true); renderChart(); renderNightDetail(); renderLegend();
    const ll = S.tracks.flatMap(o => o.ll).concat(S.impacts.map(o => [o.m.lat, o.m.lon]));
    if (ll.length) map.fitBounds(L.latLngBounds(ll).pad(0.08), { maxZoom: 7, paddingTopLeft: [0, 40], paddingBottomRight: [0, 80] });
    document.querySelector('#nights li.on')?.scrollIntoView({ block: 'nearest' });
  }
  document.querySelectorAll('.tabs button').forEach(b => b.classList.toggle('on', b.dataset.mode === S.mode));
  document.body.dataset.mode = S.mode;
  renderNightList();
}

// ---------- старт ----------
(async () => {
  const [geo, alerts, index] = await Promise.all(['data/oblasts.geojson', 'data/alerts.json', 'data/index.json']
    .map(u => fetch(u, { cache: 'no-cache' }).then(r => r.json())));
  S.geo = geo; S.alerts = alerts; S.index = index.nights || [];
  oblLayer = L.geoJSON(geo, { pane: 'obl', style: { color: '#56606e', weight: 0.8, fillOpacity: 0 },
    onEachFeature: (f, l) => {
      l.bindTooltip(() => oblTooltip(l), { sticky: true, opacity: 1 });
    } }).addTo(gObl);
  const N = S.index;
  const upd = new Date(alerts.updated).toLocaleString('ru-RU', { timeZone: 'Europe/Kyiv', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  $('#period').textContent = `прилёты с 2022 по городам и сёлам${N.length ? ` · траектории: ночи ${nightLabel(N[0].night)} – ${nightLabel(N[N.length - 1].night)}` : ''}`;
  route();
})();
