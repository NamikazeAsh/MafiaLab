'use strict';
(function () {
  // ------------------------------------------------------------------ helpers
  const $ = (s, el) => (el || document).querySelector(s);
  const $$ = (s, el) => Array.from((el || document).querySelectorAll(s));
  const esc = (s) =>
    String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

  const ROLE_LABEL = { villager: 'a Villager', mafia: 'one of the Mafia', doctor: 'the Doctor', detective: 'the Detective' };
  const ROLE_CHIP = { villager: 'Villager', mafia: 'Mafia', doctor: 'Doctor', detective: 'Detective' };

  // mode defaults to mystery (secrets hidden) until the user picks a mode in the lobby.
  const prefs = { mode: 'mystery', modeChosen: false, thoughts: true, speed: 1, motion: 'auto', random: null };
  try { Object.assign(prefs, JSON.parse(localStorage.getItem('mafia-ui') || '{}')); } catch (e) { /* storage may be blocked */ }
  if (!prefs.modeChosen) prefs.mode = 'mystery';
  function savePrefs() { try { localStorage.setItem('mafia-ui', JSON.stringify(prefs)); } catch (e) { /* ignore */ } }

  async function api(path, opts) {
    opts = opts || {};
    const init = { method: 'GET', headers: {} };
    if (opts.body !== undefined) {
      init.method = 'POST';
      init.body = JSON.stringify(opts.body);
      init.headers['Content-Type'] = 'application/json';
      init.headers['X-Mafia-UI'] = '1';
    }
    const r = await fetch(path, init);
    let data = null;
    try { data = await r.json(); } catch (e) { /* not json */ }
    if (!r.ok) throw new Error((data && data.error) || 'Request failed (' + r.status + ')');
    return data;
  }

  // ------------------------------------------------------------------ app state
  const S = {
    view: 'home',
    source: null, // 'live' | 'replay'
    gameId: null,
    events: [],
    playhead: 0,
    playing: false,
    timer: null,
    es: null,
    running: false,
    final: null,
    tab: 'chat',
    stageKey: '',
    cardKey: '',
    derived: null,
    markerCount: -1,
  };

  // ------------------------------------------------------------------ event helpers
  function stripSpeaker(ev) {
    let t = String(ev.text || '').replace(/^\[mafia\]\s*/, '').replace(/^\(thinks\)\s*/, '');
    const sp = ev.data && ev.data.speaker;
    if (sp && t.indexOf(sp + ':') === 0) t = t.slice(sp.length + 1).trim();
    return t;
  }
  const msgOf = (ev) => (ev.data && ev.data.message != null ? ev.data.message : stripSpeaker(ev));
  const thoughtOf = (ev) => (ev.data && ev.data.thought != null ? ev.data.thought : stripSpeaker(ev));

  const NEVER_STOP = new Set(['setup', 'kill_rule', 'kill_split', 'kill_vote']);
  const SECRET = new Set(['mafia_chat', 'kill_decision', 'save', 'investigate', 'thought']);
  // Playback pauses on "stop" events; the others are folded into the state silently.
  function isStop(ev) {
    if (NEVER_STOP.has(ev.kind)) return false;
    if (prefs.mode === 'mystery' && SECRET.has(ev.kind)) return false;
    if (ev.kind === 'thought' && !prefs.thoughts) return false;
    return true;
  }
  function delayFor(ev) {
    switch (ev.kind) {
      case 'speech': case 'mafia_chat': return clamp(1200 + msgOf(ev).length * 26, 1800, 7000);
      case 'thought': return clamp(900 + thoughtOf(ev).length * 16, 1200, 4500);
      case 'phase': return 1800;
      case 'death': return 3400;
      case 'no_death': case 'no_lynch': return 1800;
      case 'vote': return 380;
      case 'kill_decision': return 1300;
      case 'save': case 'investigate': return 1100;
      case 'start': return 800;
      case 'end': return 3000;
      default: return 500;
    }
  }

  // ------------------------------------------------------------------ derive
  // Pure: everything on screen at a given playhead is computed from events[0..upto].
  function derive(events, upto) {
    const full = prefs.mode === 'full';
    const setupEv = events[0] && events[0].kind === 'setup' ? events[0] : null;
    const setup = setupEv ? setupEv.data : { players: [], roles: {}, personas: {} };
    const players = (setup.players || []).map((name, i) => ({
      name, i,
      color: Crew.COLORS[i % Crew.COLORS.length],
      role: (setup.roles || {})[name] || null,
      persona: (setup.personas || {})[name] || '',
      alive: true, revealed: false, cause: null,
    }));
    const byName = {};
    players.forEach((p) => { byName[p.name] = p; });
    const st = {
      players, byName, setup, phase: 'pre', day: 0, card: null, speaker: null,
      chat: [], votes: {}, results: {}, nights: {}, marks: {}, winner: null, last: null,
    };
    const night = (d) => (st.nights[d] = st.nights[d] || { kills: [], decision: null, save: null, check: null, outcome: null });
    const addMark = (name, kind) => { if (name) (st.marks[name] = st.marks[name] || []).push(kind); };

    const end = Math.min(upto, events.length - 1);
    for (let i = 0; i <= end; i++) {
      const ev = events[i];
      const d = ev.data || {};
      st.last = ev;
      switch (ev.kind) {
        case 'start':
          st.chat.push({ t: 'sys', text: 'Game start' });
          st.card = { t: 'banner', title: 'Game start', sub: 'Find the mafia' };
          break;
        case 'phase': {
          st.phase = ev.phase; st.day = ev.day; st.speaker = null; st.marks = {};
          const night_ = ev.phase === 'night';
          st.card = { t: 'banner', title: (night_ ? 'Night ' : 'Day ') + ev.day, sub: night_ ? 'Everyone goes to sleep' : 'Emergency meeting' };
          st.chat.push({ t: 'sys', cls: 'phase', text: night_ ? 'Night ' + ev.day : 'Day ' + ev.day });
          break;
        }
        case 'speech':
          st.speaker = d.speaker;
          st.card = { t: 'say', name: d.speaker, text: msgOf(ev) };
          st.chat.push({ t: 'say', name: d.speaker, text: msgOf(ev) });
          break;
        case 'mafia_chat':
          if (!full) break;
          st.speaker = d.speaker;
          st.card = { t: 'mafia', name: d.speaker, text: msgOf(ev) };
          st.chat.push({ t: 'mafia', name: d.speaker, text: msgOf(ev) });
          break;
        case 'thought':
          if (!full || !prefs.thoughts) break;
          st.speaker = d.speaker;
          st.card = { t: 'think', name: d.speaker, text: thoughtOf(ev) };
          st.chat.push({ t: 'think', name: d.speaker, text: thoughtOf(ev) });
          break;
        case 'kill_vote':
          if (!full) break;
          {
            const n = night(ev.day);
            let round = n.kills[n.kills.length - 1];
            // A voter appearing twice means the mafia disagreed and a new round began.
            if (!round || round.some((v) => v.voter === d.voter)) { round = []; n.kills.push(round); }
            round.push({ voter: d.voter, target: d.target });
          }
          break;
        case 'kill_decision':
          if (!full) break;
          night(ev.day).decision = d.target;
          addMark(d.target, 'kill');
          st.chat.push({ t: 'sys', cls: 'kill', text: 'Mafia chose to kill ' + d.target });
          break;
        case 'save':
          if (!full) break;
          night(ev.day).save = { actor: d.actor, target: d.target };
          addMark(d.target, 'save');
          st.chat.push({ t: 'sys', cls: 'save', text: (d.actor || 'Doctor') + ' protects ' + d.target });
          break;
        case 'investigate':
          if (!full) break;
          night(ev.day).check = { actor: d.actor, target: d.target, result: d.result };
          addMark(d.target, 'check');
          st.chat.push({ t: 'sys', cls: 'check', text: (d.actor || 'Detective') + ' checks ' + d.target + ': ' + d.result });
          break;
        case 'vote': {
          const first = !st.votes[ev.day];
          (st.votes[ev.day] = st.votes[ev.day] || []).push({ voter: d.voter, target: d.target });
          st.speaker = null;
          if (first) st.card = { t: 'banner', title: 'Voting', sub: 'Votes are revealed' };
          break;
        }
        case 'death': {
          const p = byName[d.victim];
          const cause = d.cause || (/voted/.test(ev.text || '') ? 'vote' : 'night');
          if (p) { p.alive = false; p.revealed = true; p.role = d.role || p.role; p.cause = cause; }
          st.speaker = null;
          const label = ROLE_LABEL[d.role] || d.role || 'unknown';
          st.card = {
            t: 'banner', tone: cause === 'vote' ? 'eject' : 'kill',
            title: d.victim + (cause === 'vote' ? ' was ejected' : ' was killed'),
            sub: d.victim + ' was ' + label,
          };
          st.chat.push({ t: 'sys', cls: cause === 'vote' ? 'death-vote' : 'death-night', text: d.victim + (cause === 'vote' ? ' was voted out' : ' was killed in the night') + '. They were ' + (ROLE_CHIP[d.role] || d.role) + '.' });
          if (cause === 'vote') st.results[ev.day] = { out: d.victim, role: d.role };
          else night(ev.day).outcome = { killed: d.victim };
          break;
        }
        case 'no_death': {
          const n = night(ev.day);
          n.outcome = { killed: null, saved: !!(n.decision && n.save && n.save.target === n.decision) };
          st.card = { t: 'banner', title: 'Nobody died', sub: 'The night was quiet' };
          st.chat.push({ t: 'sys', text: 'Nobody died last night' });
          break;
        }
        case 'no_lynch':
          st.results[ev.day] = { out: null };
          st.card = { t: 'banner', title: 'No one was ejected', sub: 'The vote was tied or empty' };
          st.chat.push({ t: 'sys', text: 'The vote was tied or empty. Nobody is ejected.' });
          break;
        case 'end':
          st.phase = 'over'; st.winner = d.winner; st.speaker = null;
          players.forEach((p) => { p.revealed = true; if (d.roles && d.roles[p.name]) p.role = d.roles[p.name]; });
          st.card = {
            t: 'banner', tone: 'win-' + d.winner,
            title: d.winner === 'town' ? 'Town wins' : 'Mafia wins',
            sub: d.winner === 'town' ? 'All the mafia are gone' : 'The mafia have taken over',
          };
          st.chat.push({ t: 'sys', cls: 'win', text: (d.winner === 'town' ? 'Town' : 'Mafia') + ' wins' });
          break;
        default:
          break;
      }
    }
    return st;
  }

  // ------------------------------------------------------------------ rendering: stage
  function buildStage(st) {
    const key = st.players.map((p) => p.name).join(',');
    if (key === S.stageKey) return;
    S.stageKey = key;
    const ring = $('#ring');
    ring.innerHTML = '';
    const n = st.players.length;
    const big = n >= 9; // more players: smaller characters on a wider ring so neighbors do not overlap
    st.players.forEach((p, i) => {
      const a = -Math.PI / 2 + (2 * Math.PI * i) / n;
      const el = document.createElement('div');
      el.className = 'crew' + (big ? ' small' : '');
      el.dataset.name = p.name;
      el.style.left = 50 + (big ? 41 : 40) * Math.cos(a) + '%';
      el.style.top = 50 + (big ? 39 : 37) * Math.sin(a) + '%';
      el.innerHTML =
        '<div class="vote-badge"></div><div class="marks"></div><div class="body"></div>' +
        '<div class="tag"><span class="dot" style="background:' + p.color.c + '"></span><span class="name">' + esc(p.name) + '</span></div>' +
        '<div class="role-chip"></div>';
      ring.appendChild(el);
    });
    S.cardKey = '';
  }

  function renderStage(st) {
    buildStage(st);
    const full = prefs.mode === 'full';
    const stage = $('#stage');
    stage.className = 'stage ' + (st.phase === 'night' ? 'night' : st.phase === 'over' ? 'over' : 'day');

    const today = st.votes[st.day] || [];
    const counts = {};
    today.forEach((v) => { if (v.target) counts[v.target] = (counts[v.target] || 0) + 1; });

    st.players.forEach((p) => {
      const el = $('.crew[data-name="' + CSS.escape(p.name) + '"]');
      if (!el) return;
      const showRole = (full || p.revealed) && p.role;
      const body = $('.body', el);
      const wantDead = !p.alive;
      if (el._dead !== wantDead || !body.firstChild) {
        body.innerHTML = Crew.svg(p.color.c, { dead: wantDead });
        el._dead = wantDead;
      }
      el.classList.toggle('dead', !p.alive);
      el.classList.toggle('speaking', p.alive && st.speaker === p.name);
      el.classList.toggle('evil', !!(showRole && p.role === 'mafia'));
      const chip = $('.role-chip', el);
      chip.className = 'role-chip' + (showRole ? ' show role-' + p.role : '');
      chip.textContent = showRole ? ROLE_CHIP[p.role] || p.role : '';
      el.title = p.name + (showRole ? ' (' + (ROLE_CHIP[p.role] || p.role) + ')' : '') + (full && p.persona ? '\nStyle: ' + p.persona : '');
      const badge = $('.vote-badge', el);
      const c = st.phase === 'day' ? counts[p.name] || 0 : 0;
      badge.classList.toggle('show', c > 0);
      badge.textContent = c > 0 ? String(c) : '';
      const marks = full && st.phase === 'night' ? st.marks[p.name] || [] : [];
      const uniq = Array.from(new Set(marks));
      $('.marks', el).innerHTML = uniq.map((m) => '<span class="mark ' + m + '">' + m + '</span>').join('');
    });
    renderCard(st);
  }

  function renderCard(st) {
    const c = st.card;
    const key = JSON.stringify(c);
    if (key === S.cardKey) return;
    S.cardKey = key;
    const el = $('#card');
    if (!c) { el.innerHTML = ''; return; }
    if (c.t === 'banner') {
      el.innerHTML = '<div class="banner ' + (c.tone ? 'tone-' + c.tone : '') + '"><div class="b-title">' + esc(c.title) + '</div><div class="b-sub">' + esc(c.sub || '') + '</div></div>';
      return;
    }
    const p = st.byName[c.name];
    const label = c.t === 'mafia' ? 'Mafia channel' : c.t === 'think' ? 'Thinking' : '';
    el.innerHTML =
      '<div class="say ' + (c.t === 'say' ? '' : c.t) + '"><div class="who"><span class="dot" style="background:' + (p ? p.color.c : '#888') + '"></span>' +
      esc(c.name) + (label ? '<span class="label">' + label + '</span>' : '') + '</div><div class="txt">' + esc(c.text) + '</div></div>';
  }

  // ------------------------------------------------------------------ rendering: sidebar
  function dot(p) { return '<span class="dot" style="background:' + (p ? p.color.c : '#888') + '"></span>'; }

  function renderChat(st) {
    const box = $('#tab-chat');
    if (!st.chat.length) { box.innerHTML = '<div class="muted">Waiting for the game to start.</div>'; return; }
    box.innerHTML = st.chat.map((m) => {
      if (m.t === 'sys') return '<div class="sys ' + (m.cls || '') + '"><span>' + esc(m.text) + '</span></div>';
      const p = st.byName[m.name];
      return '<div class="msg ' + (m.t === 'say' ? '' : m.t) + '">' + dot(p) + '<div><div class="mname">' + esc(m.name) + '</div><div class="mtext">' + esc(m.text) + '</div></div></div>';
    }).join('');
    box.scrollTop = box.scrollHeight;
  }

  function renderVotes(st) {
    const box = $('#tab-votes');
    const days = Object.keys(st.votes).map(Number).sort((a, b) => a - b);
    if (!days.length) { box.innerHTML = '<div class="muted">No votes yet. Votes are revealed together at the end of each day.</div>'; return; }
    box.innerHTML = days.map((day) => {
      const groups = {};
      st.votes[day].forEach((v) => { const k = v.target || ''; (groups[k] = groups[k] || []).push(v.voter); });
      const rows = Object.keys(groups).sort((a, b) => groups[b].length - groups[a].length).map((t) => {
        const p = st.byName[t];
        const voters = groups[t].map((v) => '<span class="chip">' + dot(st.byName[v]) + esc(v) + '</span>').join('');
        const head = t ? dot(p) + esc(t) + '<span class="vcount">' + groups[t].length + '</span>' : 'No vote';
        return '<div class="vrow"><div class="vtarget">' + head + '</div><div class="vvoters">' + voters + '</div></div>';
      }).join('');
      const r = st.results[day];
      const res = r ? '<div class="vresult">' + (r.out ? esc(r.out) + ' was ejected' + (r.role ? ' (' + esc(ROLE_CHIP[r.role] || r.role) + ')' : '') : 'No one was ejected') + '</div>' : '';
      return '<div class="vday"><h4>Day ' + day + '</h4>' + rows + res + '</div>';
    }).join('');
    box.scrollTop = box.scrollHeight;
  }

  function renderNights(st) {
    const box = $('#tab-nights');
    if (prefs.mode !== 'full') { box.innerHTML = '<div class="muted">Night actions are hidden in mystery mode. Switch to full view to see them.</div>'; return; }
    const days = Object.keys(st.nights).map(Number).sort((a, b) => a - b);
    if (!days.length) { box.innerHTML = '<div class="muted">Night actions appear here as they happen.</div>'; return; }
    box.innerHTML = days.map((day) => {
      const n = st.nights[day];
      const lines = [];
      n.kills.forEach((round, ri) => {
        const label = n.kills.length > 1 ? 'Round ' + (ri + 1) + ': ' : 'Mafia votes: ';
        lines.push('<div class="nline">' + label + round.map((k) => '<b>' + esc(k.voter) + '</b> to ' + esc(k.target)).join(', ') + '</div>');
      });
      if (n.decision) lines.push('<div class="nline">Target: <b>' + esc(n.decision) + '</b></div>');
      if (n.save) lines.push('<div class="nline"><b>' + esc(n.save.actor || 'Doctor') + '</b> protects ' + esc(n.save.target) + '</div>');
      if (n.check) lines.push('<div class="nline"><b>' + esc(n.check.actor || 'Detective') + '</b> checks ' + esc(n.check.target) + ': ' + esc(n.check.result) + '</div>');
      if (n.outcome) {
        if (n.outcome.killed) lines.push('<div class="nline outcome bad">' + esc(n.outcome.killed) + ' was killed</div>');
        else lines.push('<div class="nline outcome good">' + (n.outcome.saved ? 'The doctor saved the target. Nobody died.' : 'Nobody died.') + '</div>');
      }
      return '<div class="nday"><h4>Night ' + day + '</h4>' + lines.join('') + '</div>';
    }).join('');
    box.scrollTop = box.scrollHeight;
  }

  // The lobby and the in game bar show the same choice.
  function syncModeUI() {
    [['#mode-full', 'full'], ['#mode-mystery', 'mystery'], ['#home-full', 'full'], ['#home-mystery', 'mystery']].forEach(([sel, m]) => {
      const el = $(sel);
      if (!el) return;
      el.classList.toggle('on', prefs.mode === m);
      el.setAttribute('aria-checked', String(prefs.mode === m));
    });
  }

  // ------------------------------------------------------------------ rendering: controls
  function renderMarkers() {
    const n = S.events.length;
    if (n === S.markerCount) return;
    S.markerCount = n;
    const scrub = $('#scrub');
    scrub.max = String(Math.max(0, n - 1));
    const span = Math.max(1, n - 1);
    $('#markers').innerHTML = S.events.map((ev, i) => {
      let cls = null;
      if (ev.kind === 'phase') cls = ev.phase === 'night' ? 'night' : 'day';
      else if (ev.kind === 'death') cls = (ev.data && ev.data.cause === 'vote') ? 'vote' : 'kill';
      else if (ev.kind === 'end') cls = 'end';
      if (!cls) return '';
      const tip = ev.kind === 'phase' ? (ev.phase === 'night' ? 'Night ' : 'Day ') + ev.day : ev.kind === 'end' ? 'Game over' : (ev.data.victim + (cls === 'vote' ? ' ejected' : ' killed'));
      return '<span class="marker ' + cls + '" style="left:' + (i / span) * 100 + '%" title="' + esc(tip) + '"></span>';
    }).join('');
  }

  function renderControls(st) {
    renderMarkers();
    $('#scrub').value = String(S.playhead);
    $('#c-play').textContent = S.playing ? 'Pause' : 'Play';
    $('#c-speed').value = String(prefs.speed);
    const where = st.phase === 'pre' ? 'Setting up' : st.phase === 'over' ? 'Game over' : (st.phase === 'night' ? 'Night ' : 'Day ') + st.day;
    $('#pos').textContent = where + '  |  event ' + (S.events.length ? S.playhead + 1 : 0) + ' of ' + S.events.length;
    syncModeUI();
    const chk = $('#chk-thoughts');
    chk.checked = prefs.thoughts && prefs.mode === 'full';
    chk.disabled = prefs.mode !== 'full';
    $('#btn-stop').classList.toggle('hidden', !(S.source === 'live' && S.running));

    let cls = 'replay', text = 'REPLAY';
    if (S.source === 'live' && S.running) { cls = 'live'; text = 'LIVE'; }
    else if (S.final && S.final.status === 'error') { cls = 'err'; text = 'ERROR'; }
    else if (S.final && S.final.status === 'stopped') { cls = 'stop'; text = 'STOPPED'; }
    else if (S.source === 'live') { cls = 'replay'; text = 'FINISHED'; }
    const pill = $('#status-pill');
    pill.className = 'pill ' + cls;
    pill.textContent = text;
    $('#demo-pill').classList.toggle('hidden', !(st.setup && st.setup.model === 'random'));
  }

  function render() {
    const at = clamp(S.playhead, 0, Math.max(0, S.events.length - 1));
    const st = derive(S.events, at);
    S.derived = st;
    renderStage(st);
    renderChat(st);
    renderVotes(st);
    renderNights(st);
    renderControls(st);
    return st;
  }

  // ------------------------------------------------------------------ effects
  function playEffect(ev, st) {
    if (ev.kind !== 'death') return;
    const p = st.byName[ev.data.victim];
    if (!p) return;
    const stage = $('#stage');
    if (p.cause === 'vote') {
      const dur = Math.max(0.9, 2.6 / prefs.speed);
      const div = document.createElement('div');
      div.className = 'eject';
      div.style.setProperty('--dur', dur + 's');
      div.innerHTML =
        '<div class="stars"></div><div class="eject-crew">' + Crew.svg(p.color.c) + '</div>' +
        '<div class="eject-text">' + esc(p.name) + ' was ejected.</div>' +
        '<div class="eject-sub">' + esc(p.name) + ' was ' + esc(ROLE_LABEL[ev.data.role] || ev.data.role || 'unknown') + '.</div>';
      stage.appendChild(div);
      setTimeout(() => div.remove(), dur * 1000 + 400);
    } else {
      const div = document.createElement('div');
      div.className = 'flash';
      stage.appendChild(div);
      setTimeout(() => div.remove(), 900);
      const el = $('.crew[data-name="' + CSS.escape(p.name) + '"]');
      if (el) { el.classList.add('just-died'); setTimeout(() => el.classList.remove('just-died'), 700); }
    }
  }

  // ------------------------------------------------------------------ playback
  function goTo(i, opts) {
    if (!S.events.length) { render(); return; }
    S.playhead = clamp(i, 0, S.events.length - 1);
    const st = render();
    if (opts && opts.animate) playEffect(S.events[S.playhead], st);
  }

  function nextStop(from) {
    for (let i = from; i < S.events.length; i++) if (isStop(S.events[i])) return i;
    return -1;
  }
  function prevStop(from) {
    for (let i = from; i >= 0; i--) if (isStop(S.events[i])) return i;
    return 0;
  }

  function schedule() {
    clearTimeout(S.timer);
    S.timer = null;
    if (!S.playing) return;
    const nxt = nextStop(S.playhead + 1);
    if (nxt === -1) {
      if (!S.running) { S.playing = false; render(); }
      return; // live: onArrive() resumes when the next event lands
    }
    const cur = S.events[S.playhead];
    const wait = cur && isStop(cur) ? delayFor(cur) / prefs.speed : 0;
    S.timer = setTimeout(() => {
      S.timer = null;
      goTo(nxt, { animate: true });
      schedule();
    }, wait);
  }

  function setPlaying(on) {
    S.playing = on;
    if (on && !S.running && S.playhead >= S.events.length - 1) goTo(0); // replay from the top
    schedule();
    render();
  }

  function onArrive() {
    if (S.playhead === 0 && S.events.length === 1) goTo(0);
    else renderMarkers();
    if (S.playing && !S.timer) schedule();
    renderControls(S.derived || derive(S.events, S.playhead));
  }

  function onFinished() {
    const f = S.final || {};
    const n = $('#notice');
    n.classList.add('hidden');
    n.classList.remove('err');
    if (f.status === 'error') {
      n.textContent = f.message || 'The game stopped because of an error.';
      n.classList.add('err');
      n.classList.remove('hidden');
    } else if (f.status === 'stopped') {
      n.textContent = 'Game stopped early.';
      n.classList.remove('hidden');
    } else if (f.calls != null) {
      const tokens = (f.prompt_tokens || 0) + (f.completion_tokens || 0);
      n.textContent = 'Finished. ' + f.calls + ' model calls, ' + tokens.toLocaleString() + ' tokens, ' + f.invalid_actions + ' invalid actions.';
      n.classList.remove('hidden');
    }
    schedule();
    render();
    refreshGames();
  }

  // ------------------------------------------------------------------ opening games
  function resetGame() {
    clearTimeout(S.timer);
    S.timer = null;
    if (S.es) { S.es.close(); S.es = null; }
    Object.assign(S, { events: [], playhead: 0, playing: false, running: false, final: null, stageKey: '', cardKey: '', markerCount: -1, derived: null });
    $('#notice').classList.add('hidden');
    $('#ring').innerHTML = '';
    $('#card').innerHTML = '';
  }

  function showView(v) {
    S.view = v;
    $('#home').classList.toggle('hidden', v !== 'home');
    $('#game').classList.toggle('hidden', v !== 'game');
  }

  function setTab(name) {
    S.tab = name;
    $$('.tab').forEach((t) => t.classList.toggle('active', t.dataset.tab === name));
    ['chat', 'votes', 'nights'].forEach((t) => $('#tab-' + t).classList.toggle('hidden', t !== name));
  }

  function openLive(gameId) {
    resetGame();
    S.source = 'live';
    S.gameId = gameId;
    S.running = true;
    S.playing = true;
    showView('game');
    render();
    const es = new EventSource('/api/live');
    S.es = es;
    let finished = false;
    es.onmessage = (e) => { S.events.push(JSON.parse(e.data)); onArrive(); };
    es.addEventListener('done', (e) => {
      finished = true;
      S.final = JSON.parse(e.data);
      S.running = false;
      es.close();
      S.es = null;
      onFinished();
    });
    es.onerror = () => {
      if (finished) return;
      es.close();
      S.es = null;
      S.running = false;
      S.final = { status: 'error', message: 'Lost the connection to the server.' };
      onFinished();
    };
  }

  async function openReplay(gameId, opts) {
    opts = opts || {};
    resetGame();
    S.source = 'replay';
    S.gameId = gameId;
    const data = await api('/api/games/' + encodeURIComponent(gameId));
    S.events = data.events;
    showView('game');
    goTo(opts.at != null ? opts.at : 0);
    S.playing = !opts.paused;
    schedule();
    render();
  }

  async function startGame(cfg) {
    const res = await api('/api/start', { body: cfg });
    openLive(res.game_id);
  }

  // ------------------------------------------------------------------ home screen
  function fmtDate(t) {
    try { return new Date(t * 1000).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }); } catch (e) { return ''; }
  }

  async function refreshGames() {
    const list = $('#games-list');
    let games = [];
    try { games = (await api('/api/games')).games; } catch (e) { list.innerHTML = '<div class="empty">Could not load games.</div>'; return; }
    try {
      const status = await api('/api/status');
      $('#btn-watch').classList.toggle('hidden', !status.running);
      $('#btn-start').disabled = !!status.running;
    } catch (e) { /* ignore */ }
    if (!games.length) { list.innerHTML = '<div class="empty">No games yet. Start one on the left.</div>'; return; }
    list.innerHTML = games.map((g) => {
      // In mystery mode the list must not spoil the result either.
      const spoilers = prefs.mode === 'full';
      const tag = g.running ? '<span class="tag-pill live">Live</span>'
        : g.winner && spoilers ? '<span class="tag-pill ' + g.winner + '">' + esc(g.winner) + ' won</span>'
        : g.winner ? '<span class="tag-pill none">Finished</span>'
        : '<span class="tag-pill none">Unfinished</span>';
      return '<button type="button" class="game-card" data-id="' + esc(g.id) + '" data-running="' + (g.running ? '1' : '') + '">' +
        '<div class="gc-main"><div class="gc-title">' + g.players + ' players, ' + (g.mafia == null ? '?' : g.mafia) + ' mafia' + (g.model ? ' | ' + esc(g.model) : '') + '</div>' +
        '<div class="gc-meta">' + esc(fmtDate(g.modified)) + ' | ' + g.days + (g.days === 1 ? ' day' : ' days') + ' | ' + esc(g.id) + '</div></div>' + tag + '</button>';
    }).join('');
  }

  function readForm() {
    const num = (id) => { const v = $(id).value.trim(); return v === '' ? null : Number(v); };
    return {
      players: Number($('#f-players').value),
      mafia: num('#f-mafia'),
      seed: num('#f-seed'),
      model: $('#f-model').value.trim(),
      rpm: num('#f-rpm'),
      random: $('#f-random').checked,
      delay: Number($('#f-delay').value),
    };
  }

  function syncForm() { $('#start-form').classList.toggle('random', $('#f-random').checked); }

  // ------------------------------------------------------------------ wiring
  function goHome() {
    resetGame();
    showView('home');
    history.replaceState(null, '', location.pathname);
    refreshGames();
  }

  function wire() {
    $('#brand').addEventListener('click', goHome);
    $('#btn-back').addEventListener('click', goHome);
    $('#btn-refresh').addEventListener('click', refreshGames);
    $('#f-random').addEventListener('change', () => { prefs.random = $('#f-random').checked; savePrefs(); syncForm(); });

    $('#start-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const err = $('#form-error');
      err.classList.add('hidden');
      try { await startGame(readForm()); } catch (ex) { err.textContent = ex.message; err.classList.remove('hidden'); }
    });
    $('#btn-watch').addEventListener('click', () => openLive(null));
    $('#games-list').addEventListener('click', (e) => {
      const card = e.target.closest('.game-card');
      if (!card) return;
      if (card.dataset.running) openLive(card.dataset.id);
      else openReplay(card.dataset.id).catch((ex) => alert(ex.message));
    });

    $$('.tab').forEach((t) => t.addEventListener('click', () => setTab(t.dataset.tab)));

    const setMode = (m) => {
      prefs.mode = m;
      prefs.modeChosen = true;
      savePrefs();
      S.cardKey = '';
      syncModeUI();
      schedule();
      render();
    };
    // Revealing everything mid game asks first, so nobody spoils it with a stray click.
    $('#mode-full').addEventListener('click', () => {
      if (prefs.mode === 'full') return;
      if (window.confirm('Switch to full view? This reveals every role, secret chat, and private thought.')) setMode('full');
    });
    $('#mode-mystery').addEventListener('click', () => setMode('mystery'));
    const lobbyMode = (m) => { prefs.mode = m; prefs.modeChosen = true; savePrefs(); syncModeUI(); refreshGames(); };
    $('#home-mystery').addEventListener('click', () => lobbyMode('mystery'));
    $('#home-full').addEventListener('click', () => lobbyMode('full'));
    $('#chk-thoughts').addEventListener('change', (e) => { prefs.thoughts = e.target.checked; savePrefs(); S.cardKey = ''; schedule(); render(); });
    $('#btn-stop').addEventListener('click', () => api('/api/stop', { body: {} }).catch(() => {}));

    $('#chk-motion').addEventListener('change', (e) => { prefs.motion = e.target.checked ? 'on' : 'off'; savePrefs(); applyMotion(); });

    $('#c-play').addEventListener('click', () => setPlaying(!S.playing));
    $('#c-start').addEventListener('click', () => { clearTimeout(S.timer); S.timer = null; goTo(0); schedule(); });
    $('#c-end').addEventListener('click', () => { clearTimeout(S.timer); S.timer = null; goTo(S.events.length - 1); schedule(); });
    const step = (dir) => {
      clearTimeout(S.timer); S.timer = null;
      const i = dir > 0 ? nextStop(S.playhead + 1) : prevStop(S.playhead - 1);
      if (i >= 0) goTo(i, { animate: dir > 0 });
      schedule();
    };
    $('#c-next').addEventListener('click', () => step(1));
    $('#c-prev').addEventListener('click', () => step(-1));
    $('#c-speed').addEventListener('change', (e) => { prefs.speed = Number(e.target.value); savePrefs(); schedule(); });
    $('#scrub').addEventListener('input', (e) => { clearTimeout(S.timer); S.timer = null; goTo(Number(e.target.value)); schedule(); });

    document.addEventListener('keydown', (e) => {
      if (S.view !== 'game' || /INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName)) return;
      if (e.code === 'Space') { e.preventDefault(); setPlaying(!S.playing); }
      else if (e.code === 'ArrowRight') step(1);
      else if (e.code === 'ArrowLeft') step(-1);
    });
  }

  function applyPrefsToForm() {
    $('#c-speed').value = String(prefs.speed);
  }

  // Animations follow the system "reduce motion" setting until the user picks a side.
  function applyMotion() {
    const os = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    const off = prefs.motion === 'off' || (prefs.motion !== 'on' && os);
    document.documentElement.classList.toggle('no-motion', off);
    $('#chk-motion').checked = !off;
  }

  // Deep link: #game=game_123&at=40&mode=mystery&paused=1&tab=votes&thoughts=0
  // Returns true if it opened a replay.
  async function applyHash() {
    const h = new URLSearchParams(location.hash.replace(/^#/, ''));
    if (h.get('mode') === 'full' || h.get('mode') === 'mystery') prefs.mode = h.get('mode');
    if (h.get('thoughts') != null) prefs.thoughts = h.get('thoughts') !== '0';
    if (h.get('tab')) setTab(h.get('tab'));
    const game = h.get('game');
    if (!/^game_\d+$/.test(game || '')) return false;
    try {
      await openReplay(game, { at: h.get('at') != null ? Number(h.get('at')) : 0, paused: h.get('paused') === '1' });
      return true;
    } catch (e) {
      return false; // unknown game: stay where we are
    }
  }

  async function init() {
    Crew.ensureDefs();
    $('#brand-crew').innerHTML = Crew.svg(Crew.COLORS[0].c);
    wire();
    applyPrefsToForm();
    applyMotion();
    syncModeUI();
    syncForm();
    setTab('chat');

    window.addEventListener('hashchange', () => { applyHash(); });
    if (await applyHash()) return;
    render();
    try {
      const status = await api('/api/status');
      // Default to real players when a key is configured, unless the user chose otherwise before.
      $('#f-random').checked = prefs.random != null ? prefs.random : !status.has_key;
      syncForm();
      $('#key-hint').classList.toggle('hidden', !!status.has_key);
      if (status.running) { openLive(status.game_id); return; }
    } catch (e) { /* ignore */ }
    refreshGames();
  }

  init();
})();
