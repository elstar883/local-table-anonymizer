"""Локальный веб-интерфейс LTA.

Запускается только на 127.0.0.1 (loopback) — приложение полностью локальное,
интернет не используется. Никаких внешних ресурсов: весь HTML/CSS/JS встроен.
"""
import os
import re
import secrets
import threading
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request, send_file

from . import core, tableio, transform
from .project import Project, ProjectError, WrongPassword, list_projects

# LTA_DATA_DIR allows tests and CI to use an isolated directory. The default
# stays the same, so normal application behavior is unchanged.
DATA_ROOT = Path(
    os.environ.get(
        "LTA_DATA_DIR",
        Path.home() / "Library" / "Application Support" / "LocalTableAnonymizer",
    )
)
PROJECTS_DIR = DATA_ROOT / "projects"
UPLOAD_DIR = DATA_ROOT / "uploads"

PAGE = r"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Local Table Anonymizer</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%234f8cff'/%3E%3Cpath d='M16 6l8 3v7c0 5-3.4 8.6-8 10-4.6-1.4-8-5-8-10V9l8-3z' fill='%230e1118'/%3E%3Cpath d='M12 16l3 3 5-6' fill='none' stroke='%234f8cff' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E">
<style>
  :root { --bg:#0e1118; --panel:#161c28; --panel2:#1c2433; --border:#2a3446;
          --text:#e8edf7; --muted:#8a97b0; --accent:#4f8cff; --accent2:#3b6fd4;
          --ok:#2fbf71; --warn:#e0a63c; --err:#e05c5c; }
  * { box-sizing:border-box; }
  body { margin:0; font:15px/1.55 -apple-system,"Segoe UI",Roboto,sans-serif;
         background:var(--bg); color:var(--text); }
  header { position:sticky; top:0; z-index:5; padding:14px 26px; background:rgba(22,28,40,.92);
           backdrop-filter:blur(6px); border-bottom:1px solid var(--border);
           display:flex; justify-content:space-between; align-items:center; gap:16px; flex-wrap:wrap; }
  header h1 { font-size:17px; margin:0; }
  header .sub { color:var(--muted); font-size:12px; }
  .offline { display:inline-flex; align-items:center; gap:6px; color:var(--ok); font-size:12px; }
  .offline::before { content:""; width:8px; height:8px; border-radius:50%; background:var(--ok); }
  main { max-width:1100px; margin:22px auto; padding:0 18px 60px; display:grid; gap:16px; }
  .card { background:var(--panel); border:1px solid var(--border); border-radius:14px; padding:20px 22px; }
  .card h2 { margin:0 0 4px; font-size:15.5px; display:flex; align-items:center; gap:10px; }
  .card h2 .step { display:inline-flex; align-items:center; justify-content:center;
                   width:26px; height:26px; background:var(--accent); border-radius:50%; font-size:13px; }
  .card .hint { color:var(--muted); font-size:13px; margin:0 0 12px 36px; }
  .muted { color:var(--muted); font-size:13px; }
  input, select, button { font:inherit; border-radius:9px; border:1px solid var(--border);
                          background:var(--panel2); color:var(--text); padding:9px 13px; }
  input:focus, select:focus { outline:none; border-color:var(--accent); }
  input::placeholder { color:#5d6b85; }
  button { cursor:pointer; }
  button.primary { background:var(--accent); border-color:var(--accent); font-weight:600; }
  button.primary:hover { background:var(--accent2); }
  button.ghost { background:transparent; }
  button.danger { background:transparent; border-color:#6b3030; color:var(--err); }
  button.danger:hover { background:rgba(224,92,92,.12); }
  button:disabled { opacity:.45; cursor:not-allowed; }
  .row { display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
  .grid2 { display:grid; grid-template-columns:1fr 1fr; gap:18px; }
  @media (max-width:860px){ .grid2 { grid-template-columns:1fr; } }
  table { border-collapse:collapse; width:100%; margin-top:12px; font-size:13px; }
  th, td { border:1px solid var(--border); padding:7px 10px; text-align:left; }
  th { background:var(--panel2); font-weight:600; position:sticky; top:0; }
  td input, td select { padding:5px 8px; border-radius:7px; }
  .badge { display:inline-block; padding:3px 11px; border-radius:99px; font-size:12.5px;
           border:1px solid var(--border); color:var(--muted); }
  .badge.ok { color:var(--ok); border-color:rgba(47,191,113,.5); background:rgba(47,191,113,.08); }
  progress { width:100%; height:8px; margin-top:14px; accent-color:var(--accent); }
  .msg { margin-top:12px; padding:11px 14px; border-radius:10px; font-size:13.5px; display:none; white-space:pre-wrap; }
  .msg.ok   { display:block; background:rgba(47,191,113,.1);  color:var(--ok);   border:1px solid rgba(47,191,113,.4); }
  .msg.err  { display:block; background:rgba(224,92,92,.1);   color:var(--err);  border:1px solid rgba(224,92,92,.4); }
  .msg.warn { display:block; background:rgba(224,166,60,.1);  color:var(--warn); border:1px solid rgba(224,166,60,.4); }
  a { color:var(--accent); }
  .hidden { display:none !important; }
  .drop { border:2px dashed var(--border); border-radius:12px; padding:26px; text-align:center;
          color:var(--muted); transition:.15s; cursor:pointer; }
  .drop:hover, .drop.over { border-color:var(--accent); color:var(--text); background:rgba(79,140,255,.05); }
  .drop b { color:var(--text); }
  .dl { display:inline-flex; align-items:center; gap:8px; padding:10px 16px; border-radius:10px;
        background:rgba(47,191,113,.12); border:1px solid rgba(47,191,113,.5); color:var(--ok);
        text-decoration:none; font-weight:600; }
  .stat { display:inline-block; margin-right:18px; }
  .stat b { font-size:19px; }
  .kinds { display:flex; gap:6px; flex-wrap:wrap; }
  .legend { margin-top:10px; font-size:12.5px; color:var(--muted); line-height:1.7; }
  .legend code { background:var(--panel2); padding:1px 6px; border-radius:5px; color:var(--text); }
  .sec-title { font-size:12px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); margin:0 0 10px; }
  .previewwrap { max-height:300px; overflow:auto; border-radius:10px; margin-top:12px; }
  .previewwrap table { margin:0; }
  #colsBox, #anonReport, #deanonReport { overflow-x:auto; -webkit-overflow-scrolling:touch; max-width:100%; }
  #colsBox table { table-layout:fixed; min-width:560px; }
  #colsBox td select { width:100%; min-width:0; }
  #anonReport table, #deanonReport table { min-width:420px; }
  main > *, .grid2 > * { min-width:0; }
  @media (max-width:640px){
    #colsBox table { min-width:520px; }
    th, td { padding:6px 7px; }
    .card { padding:16px 14px; }
    main { padding:0 10px 40px; }
  }
  .footnote { text-align:center; color:#5d6b85; font-size:12px; margin-top:8px; }
</style>
</head>
<body>
<header>
  <div>
    <h1>Local Table Anonymizer</h1>
    <div class="sub">Обратимая анонимизация таблиц · алгоритмы, без нейросетей</div>
  </div>
  <div class="row">
    <span class="offline">работает офлайн, только на этом компьютере</span>
    <span id="projBadge" class="badge">проект не открыт</span>
  </div>
</header>
<main>
  <div id="msg" class="msg"></div>

  <section class="card">
    <h2><span class="step">1</span>Проект</h2>
    <p class="hint">Проект хранит зашифрованный словарь «псевдоним → персональные данные».
       Пароль нужен для восстановления и не может быть восстановлен при утере.</p>
    <div id="noProject" class="grid2">
      <div>
        <p class="sec-title">Новый проект</p>
        <div class="row">
          <input id="projName" placeholder="имя проекта, напр. clients" size="24">
          <input id="projPass" type="password" placeholder="пароль (мин. 8 символов)" size="22">
          <button class="primary" onclick="createProject()">Создать</button>
        </div>
      </div>
      <div>
        <p class="sec-title">Существующий проект</p>
        <div class="row">
          <select id="projList" onchange="document.getElementById('openPass').focus()"></select>
          <input id="openPass" type="password" placeholder="пароль" size="20"
                 onkeydown="if(event.key==='Enter')openProject()">
          <button onclick="openProject()">Открыть</button>
        </div>
        <div id="noProjects" class="muted" style="margin-top:8px">Пока нет проектов — создайте первый.</div>
      </div>
    </div>
    <div id="yesProject" class="row hidden">
      <button class="ghost" onclick="closeProject()">Закрыть проект</button>
      <button class="danger" onclick="destroyProject()">Уничтожить проект и словарь</button>
    </div>
  </section>

  <div class="grid2">
    <section class="card">
      <h2><span class="step">2</span>Загрузка таблицы</h2>
      <p class="hint">CSV (UTF-8, CP1251) или XLSX. Данные не покидают компьютер.</p>
      <div class="drop" id="drop" onclick="document.getElementById('srcFile').click()">
        <b>Выберите или перетащите файл</b><br>
        <span class="muted" id="dropName">таблица с персональными данными</span>
      </div>
      <input type="file" id="srcFile" accept=".csv,.xlsx" class="hidden" onchange="uploadSource()">
      <div id="srcInfo" class="muted" style="margin-top:10px"></div>
    </section>

    <section class="card">
      <h2><span class="step">3</span>Режимы обработки</h2>
      <p class="hint">Настройте, что делать со столбцами. Тип определён автоматически — при необходимости измените.</p>
      <div class="legend">
        <code>INDEX</code> — замена на индекс, обратима (для ПДн)<br>
        <code>HASH</code> — вид сохранён, значения заменены, необратимо<br>
        <code>MASK</code> — частичное скрытие звёздочками, необратимо<br>
        <code>KEEP</code> — оставить без изменений
      </div>
      <div id="colsBox"></div>
    </section>
  </div>

  <section class="card">
    <h2><span class="step">4</span>Анонимизация</h2>
    <p class="hint">Заменит персональные данные по настройкам и подготовит файл для скачивания.</p>
    <div class="row">
      <button class="primary" id="btnAnon" onclick="anonymize()" disabled>Анонимизировать</button>
      <span class="muted" id="anonHint">сначала загрузите таблицу</span>
    </div>
    <progress id="progAnon" max="100" value="0" class="hidden"></progress>
    <div id="anonReport"></div>
  </section>

  <section class="card">
    <h2><span class="step">5</span>Возврат персональных данных</h2>
    <p class="hint">Загрузите анонимную таблицу — приложение восстановит ПДн из словаря проекта.</p>
    <div class="row">
      <button class="primary" id="btnDeanon" onclick="document.getElementById('deanonFile').click()" disabled>
        Выбрать анонимную таблицу</button>
      <span class="muted" id="deanonHint">сначала откройте проект</span>
    </div>
    <input type="file" id="deanonFile" accept=".csv,.xlsx" class="hidden" onchange="deanon()">
    <progress id="progDeanon" max="100" value="0" class="hidden"></progress>
    <div id="deanonReport"></div>
  </section>

  <div class="footnote">Local Table Anonymizer · данные и словарь хранятся только на этом компьютере</div>
</main>
<script>
const TOKEN = {{ token|tojson }};
let HAS_SOURCE = false, PROJECT_OPEN = false;

const api  = (p, opts) => fetch(`/api/${TOKEN}` + p, opts);
const jget = async p => { const r = await api(p); return r.json(); };
const jpost = async (p, data) => { const r = await api(p, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(data||{})}); return r.json(); };

function msg(text, cls) {
  const el = document.getElementById('msg');
  el.textContent = text || ''; el.className = 'msg ' + (cls || 'ok');
  if (text) setTimeout(() => { if (el.textContent === text) el.className = 'msg'; }, 10000);
  if (text) el.scrollIntoView({behavior:'smooth', block:'nearest'});
}
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

async function refresh() {
  const s = await jget('/state');
  PROJECT_OPEN = !!s.project;
  document.getElementById('projBadge').textContent = s.project ? `проект: ${s.project}` : 'проект не открыт';
  document.getElementById('projBadge').className = 'badge' + (s.project ? ' ok' : '');
  document.getElementById('noProject').classList.toggle('hidden', PROJECT_OPEN);
  document.getElementById('yesProject').classList.toggle('hidden', !PROJECT_OPEN);

  const sel = document.getElementById('projList');
  sel.innerHTML = (s.projects || []).map(n => `<option>${esc(n.replace(/\.lta$/,''))}</option>`).join('');
  const none = (s.projects || []).length === 0;
  document.getElementById('noProjects').classList.toggle('hidden', !none);
  sel.parentElement.classList.toggle('hidden', none);

  HAS_SOURCE = !!s.source;
  document.getElementById('srcInfo').textContent = s.source
      ? `Загружено: ${s.source.filename} — ${s.source.rows} строк, ${s.source.headers.length} столбцов` : '';
  document.getElementById('dropName').textContent = s.source ? s.source.filename : 'таблица с персональными данными';
  document.getElementById('btnAnon').disabled = !(PROJECT_OPEN && HAS_SOURCE);
  document.getElementById('anonHint').textContent = HAS_SOURCE ? '' : 'сначала загрузите таблицу';
  document.getElementById('btnDeanon').disabled = !PROJECT_OPEN;
  document.getElementById('deanonHint').textContent = PROJECT_OPEN ? '' : 'сначала откройте проект';
  renderCols(s.columns || {}, s.source ? s.source.headers : []);
}

const MODE_RU = {INDEX:'INDEX — индекс (обратимо)', HASH:'HASH — замена с сохранением вида',
                  MASK:'MASK — скрытие звёздочками', KEEP:'KEEP — без изменений'};
function renderCols(columns, headers) {
  const box = document.getElementById('colsBox');
  if (!headers.length) { box.innerHTML = ''; return; }
  const kinds = ['generic','name','phone','email','date','passport','address','city'];
  const kindRu = {generic:'прочее', name:'ФИО', phone:'телефон', email:'email', date:'дата',
                  passport:'паспорт/СНИЛС', address:'адрес', city:'город'};
  box.innerHTML = `<table><tr><th style="width:26%">Столбец</th><th style="width:20%">Тип</th>
      <th style="width:36%">Режим</th><th>Пример</th></tr>` +
    headers.map(h => {
      const c = columns[h] || {};
      return `<tr>
        <td><b>${esc(h)}</b></td>
        <td><select data-h="${esc(h)}" data-f="kind" onchange="saveCols(this)">${kinds.map(k =>
            `<option ${k===(c.kind||'generic')?'selected':''}>${kindRu[k]} (${k})</option>`).join('')}</select></td>
        <td><select data-h="${esc(h)}" data-f="mode" onchange="saveCols(this)">${['INDEX','HASH','MASK','KEEP'].map(m =>
            `<option value="${m}" ${m===(c.mode||'KEEP')?'selected':''}>${MODE_RU[m]}</option>`).join('')}</select></td>
        <td class="muted">${esc(c.sample||'—')}</td></tr>`;
    }).join('') + `</table>`;
}
let saveTimer = null;
function saveCols(el) {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(async () => {
    const columns = {};
    document.querySelectorAll('#colsBox [data-h]').forEach(e => {
      const h = e.dataset.h, f = e.dataset.f;
      columns[h] = columns[h] || {};
      columns[h][f] = e.value;
    });
    const r = await jpost('/columns', {columns});
    if (r.error) msg(r.error, 'err');
  }, 150);
}

async function createProject() {
  const r = await jpost('/project/create', {
    name: document.getElementById('projName').value.trim(),
    password: document.getElementById('projPass').value});
  if (r.error) { msg(r.error, 'err'); return; }
  document.getElementById('projName').value = ''; document.getElementById('projPass').value = '';
  msg('Проект создан и открыт. Теперь загрузите таблицу (шаг 2).', 'ok');
  refresh();
}
async function openProject() {
  const r = await jpost('/project/open', {
    name: document.getElementById('projList').value,
    password: document.getElementById('openPass').value});
  if (r.error) { msg(r.error, 'err'); return; }
  document.getElementById('openPass').value = '';
  msg('Проект открыт.', 'ok');
  refresh();
}
async function closeProject() { await jpost('/project/close'); msg('Проект закрыт.', 'ok'); refresh(); }
async function destroyProject() {
  if (!confirm('Уничтожить проект и словарь безвозвратно? Восстановление ПДн станет невозможным.')) return;
  const r = await jpost('/project/destroy');
  msg(r.error || 'Проект уничтожен, словарь стёрт.', r.error ? 'err' : 'ok');
  refresh();
}

/* drag & drop */
const drop = document.getElementById('drop');
['dragenter','dragover'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('over'); }));
['dragleave','drop'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove('over'); }));
drop.addEventListener('drop', e => {
  const f = e.dataTransfer.files[0];
  if (f) { const inp = document.getElementById('srcFile'); inp.files = e.dataTransfer.files; uploadSource(); }
});

async function uploadSource() {
  if (!PROJECT_OPEN) { msg('Сначала создайте или откройте проект (шаг 1).', 'warn'); return; }
  const inp = document.getElementById('srcFile');
  const f = inp.files[0];
  if (!f) return;
  document.getElementById('srcInfo').textContent = 'Загрузка…';
  const fd = new FormData(); fd.append('file', f);
  const r = await api('/source', {method:'POST', body:fd}).then(x => x.json());
  if (r.error) { msg(r.error, 'err'); document.getElementById('srcInfo').textContent = ''; return; }
  msg('Таблица загружена. Проверьте режимы в шаге 3 и нажмите «Анонимизировать».', 'ok');
  refresh();
}

async function runJob(path, progId, onDone) {
  const prog = document.getElementById(progId);
  prog.classList.remove('hidden'); prog.value = 0;
  const start = await jpost(path, {});
  if (start.error) { prog.classList.add('hidden'); msg(start.error, 'err'); return; }
  const id = start.job;
  await new Promise(res => {
    const t = setInterval(async () => {
      const st = await jget('/progress/' + id);
      prog.value = Math.round(100 * (st.frac || 0));
      if (st.done) { clearInterval(t); prog.classList.add('hidden'); res(st); }
    }, 250);
  }).then(st => {
    if (st.error) msg(st.error, 'err'); else onDone(st);
  });
}
async function anonymize() {
  await runJob('/anonymize', 'progAnon', st => {
    const d = st.download, r = st.report;
    const cols = Object.entries(r.columns || {})
      .map(([h, c]) => `<tr><td>${esc(h)}</td><td>${c.mode}</td><td>${c.unique}</td></tr>`).join('');
    document.getElementById('anonReport').innerHTML =
      `<div style="margin-top:16px"><span class="stat"><b>${r.rows}</b><br><span class="muted">строк</span></span>
       <span class="stat"><b>${Object.keys(r.columns||{}).length}</b><br><span class="muted">столбцов обработано</span></span></div>
       ${cols ? `<table><tr><th>Столбец</th><th>Режим</th><th>Уникальных псевдонимов</th></tr>${cols}</table>` : ''}
       <div class="row" style="margin-top:14px"><a class="dl" href="/download/${TOKEN}/${d}">Скачать анонимную таблицу — ${esc(d)}</a></div>
       <div class="muted" style="margin-top:8px">Работайте с этой таблицей; вернуть ПДн можно в шаге 5, загрузив её обратно.</div>`;
    msg('Анонимизация завершена.', 'ok');
  });
}
async function deanon() {
  const f = document.getElementById('deanonFile').files[0];
  if (!f) return;
  const fd = new FormData(); fd.append('file', f);
  const up = await api('/deanon/file', {method:'POST', body:fd}).then(x => x.json());
  if (up.error) { msg(up.error, 'err'); return; }
  await runJob('/deanon', 'progDeanon', st => {
    const r = st.report;
    const byCol = Object.entries(r.by_column || {})
      .map(([h, c]) => `<tr><td>${esc(h)}</td><td>${c.restored}</td><td>${c.not_found}</td></tr>`).join('');
    document.getElementById('deanonReport').innerHTML =
      `<div style="margin-top:16px">
        <span class="stat"><b>${r.restored}</b><br><span class="muted">восстановлено</span></span>
        <span class="stat"><b>${r.not_found}</b><br><span class="muted">не найдено</span></span></div>
       ${byCol ? `<table><tr><th>Столбец</th><th>Восстановлено</th><th>Не найдено</th></tr>${byCol}</table>` : ''}
       <div class="row" style="margin-top:14px"><a class="dl" href="/download/${TOKEN}/${st.download}">Скачать восстановленную таблицу — ${esc(st.download)}</a></div>`;
    msg(r.not_found ? `Восстановлено ${r.restored}, не найдено ${r.not_found} (значения оставлены как есть).`
                    : 'Все персональные данные восстановлены.', r.not_found ? 'warn' : 'ok');
  });
  document.getElementById('deanonFile').value = '';
}
refresh();
</script>
</body>
</html>"""


def create_app(data_root: Path = None) -> Flask:
    root = Path(data_root) if data_root else PROJECTS_DIR.parent
    projects_dir = root / "projects"
    uploads_dir = root / "uploads"
    projects_dir.mkdir(parents=True, exist_ok=True)
    uploads_dir.mkdir(parents=True, exist_ok=True)

    app = Flask(__name__)
    token = secrets.token_urlsafe(12)
    state = {"project": None, "project_obj": None, "source": None, "deanon_file": None}
    jobs = {}
    jobs_lock = threading.Lock()

    def require(f):
        """Проверка токена: tok убирается из аргументов view-функции."""
        from functools import wraps

        @wraps(f)
        def wrapper(*a, **kw):
            kw.pop("tok", None)
            if request.view_args and request.view_args.get("tok") != token:
                return jsonify({"error": "bad token"}), 403
            return f(*a, **kw)

        return wrapper

    def need_project():
        if not state["project_obj"]:
            raise ProjectError("Проект не открыт")

    def ok(**extra):
        d = {"ok": True}
        d.update(extra)
        return jsonify(d)

    # ------------------------------------------------------------- страница

    @app.route("/")
    def index():
        return render_template_string(PAGE, token=token)

    # --------------------------------------------------------------- state

    @app.route("/api/<tok>/state")
    @require
    def api_state():
        cols = {}
        if state["project_obj"]:
            cols = state["project_obj"].meta.get("columns", {})
        return jsonify({
            "project": state["project"],
            "projects": list_projects(projects_dir),
            "source": state["source"],
            "columns": cols,
        })

    # -------------------------------------------------------------- проект

    @app.route("/api/<tok>/project/create", methods=["POST"])
    @require
    def api_create():
        d = request.get_json(force=True)
        name = (d.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Введите имя проекта"}), 400
        if not name.endswith(".lta"):
            name += ".lta"
        if not re.fullmatch(r"[\w\-. ]+\.lta", name):
            return jsonify({"error": "Имя проекта: только буквы, цифры, пробел, дефис, точка"}), 400
        try:
            p = Project.create(projects_dir / name, d.get("password") or "")
        except ProjectError as e:
            return jsonify({"error": str(e)}), 400
        if state["project_obj"]:
            state["project_obj"].close()
        state.update(project=name[:-4], project_obj=p, source=None, deanon_file=None)
        return ok()

    @app.route("/api/<tok>/project/open", methods=["POST"])
    @require
    def api_open():
        d = request.get_json(force=True)
        name = d.get("name") or ""
        try:
            p = Project.open(projects_dir / name, d.get("password") or "")
        except WrongPassword:
            return jsonify({"error": "Неверный пароль"}), 403
        except ProjectError as e:
            return jsonify({"error": str(e)}), 400
        if state["project_obj"]:
            state["project_obj"].close()
        state.update(project=name[:-4] if name.endswith(".lta") else name,
                     project_obj=p, source=None, deanon_file=None)
        return ok()

    @app.route("/api/<tok>/project/close", methods=["POST"])
    @require
    def api_close():
        if state["project_obj"]:
            state["project_obj"].close()
        state.update(project=None, project_obj=None, source=None, deanon_file=None)
        return ok()

    @app.route("/api/<tok>/project/destroy", methods=["POST"])
    @require
    def api_destroy():
        if state["project_obj"]:
            state["project_obj"].destroy()
        state.update(project=None, project_obj=None, source=None, deanon_file=None)
        return ok()

    # ----------------------------------------------------------- источники

    @app.route("/api/<tok>/source", methods=["POST"])
    @require
    def api_source():
        try:
            need_project()
        except ProjectError as e:
            return jsonify({"error": str(e)}), 400
        f = request.files.get("file")
        if not f or not f.filename:
            return jsonify({"error": "Файл не передан"}), 400
        suffix = Path(f.filename).suffix.lower()
        if suffix not in (".csv", ".xlsx"):
            return jsonify({"error": "Поддерживаются только .csv и .xlsx"}), 400
        tmp = uploads_dir / f"source_{secrets.token_hex(4)}{suffix}"
        f.save(str(tmp))
        try:
            headers, rows, meta = tableio.read_table(tmp)
        except Exception as e:  # noqa: BLE001
            tmp.unlink(missing_ok=True)
            return jsonify({"error": f"Ошибка чтения: {e}"}), 400
        p = state["project_obj"]
        cols = p.meta.get("columns", {})
        new_cols = {}
        for h in headers:
            i = headers.index(h)
            spec = cols.get(h, {})
            sample_vals = [str(r[i]) for r in rows[:200] if i < len(r) and str(r[i]).strip()]
            kind = spec.get("kind") or transform.guess_kind(h, sample_vals)
            new_cols[h] = {
                "mode": spec.get("mode", "INDEX" if kind != "generic" else "KEEP"),
                "kind": kind,
                "prefix": spec.get("prefix", "") or transform.default_prefix(kind),
                "sample": sample_vals[0][:40] if sample_vals else "",
            }
        p.set_columns(new_cols)
        state["source"] = {
            "filename": f.filename,
            "path": str(tmp),
            "rows": len(rows),
            "headers": headers,
            "meta": meta,
        }
        return ok(rows=len(rows), headers=headers)

    @app.route("/api/<tok>/columns", methods=["POST"])
    @require
    def api_columns():
        try:
            need_project()
        except ProjectError as e:
            return jsonify({"error": str(e)}), 400
        d = request.get_json(force=True)
        cols = state["project_obj"].meta.get("columns", {})
        for h, upd in (d.get("columns") or {}).items():
            if h in cols:
                cols[h].update({k: v for k, v in upd.items() if v != ""})
        state["project_obj"].set_columns(cols)
        return ok()

    # ------------------------------------------------------- анонимизация

    def _start_job(fn):
        job_id = secrets.token_hex(6)
        with jobs_lock:
            jobs[job_id] = {"frac": 0.0, "done": False, "error": None}

        def run():
            try:
                fn(job_id)
            except Exception as e:  # noqa: BLE001
                jobs[job_id].update(error=str(e), done=True)

        threading.Thread(target=run, daemon=True).start()
        return job_id

    @app.route("/api/<tok>/anonymize", methods=["POST"])
    @require
    def api_anonymize():
        try:
            need_project()
        except ProjectError as e:
            return jsonify({"error": str(e)}), 400
        if not state.get("source"):
            return jsonify({"error": "Сначала загрузите таблицу (шаг 2)"}), 400
        p = state["project_obj"]
        src = dict(state["source"])
        project_name = state["project"]

        def job(job_id):
            headers, rows, _meta = tableio.read_table(src["path"])

            def prog(done, total):
                jobs[job_id]["frac"] = done / max(total, 1)

            new_rows, report = core.anonymize_table(p, headers, rows, progress=prog)
            out = uploads_dir / f"{project_name}_anon.{Path(src['path']).suffix[1:]}"
            tableio.write_table(out, headers, new_rows)
            report["columns"] = {h: s for h, s in report["columns"].items()
                                 if p.meta["columns"].get(h, {}).get("mode") != "KEEP"}
            jobs[job_id].update(frac=1.0, done=True, report=report, download=out.name)

        return jsonify({"job": _start_job(job)})

    @app.route("/api/<tok>/progress/<jid>")
    @require
    def api_progress(jid):
        return jsonify(jobs.get(jid, {"error": "unknown job", "done": True}))

    # ----------------------------------------------------- деанонимизация

    @app.route("/api/<tok>/deanon/file", methods=["POST"])
    @require
    def api_deanon_file():
        try:
            need_project()
        except ProjectError as e:
            return jsonify({"error": str(e)}), 400
        f = request.files.get("file")
        if not f or not f.filename:
            return jsonify({"error": "Файл не передан"}), 400
        suffix = Path(f.filename).suffix.lower()
        if suffix not in (".csv", ".xlsx"):
            return jsonify({"error": "Поддерживаются только .csv и .xlsx"}), 400
        tmp = uploads_dir / f"deanon_{secrets.token_hex(4)}{suffix}"
        f.save(str(tmp))
        try:
            tableio.read_table(tmp)
        except Exception as e:  # noqa: BLE001
            tmp.unlink(missing_ok=True)
            return jsonify({"error": f"Ошибка чтения: {e}"}), 400
        state["deanon_file"] = str(tmp)
        return ok()

    @app.route("/api/<tok>/deanon", methods=["POST"])
    @require
    def api_deanon():
        try:
            need_project()
        except ProjectError as e:
            return jsonify({"error": str(e)}), 400
        if not state.get("deanon_file"):
            return jsonify({"error": "Сначала загрузите анонимную таблицу (шаг 5)"}), 400
        p = state["project_obj"]
        path = state["deanon_file"]
        project_name = state["project"]

        def job(job_id):
            headers, rows, _meta = tableio.read_table(path)

            def prog(done, total):
                jobs[job_id]["frac"] = done / max(total, 1)

            new_rows, report = core.deanon_table(p, headers, rows, progress=prog)
            out = uploads_dir / f"{project_name}_restored.{Path(path).suffix[1:]}"
            tableio.write_table(out, headers, new_rows)
            jobs[job_id].update(frac=1.0, done=True, report=report, download=out.name)

        return jsonify({"job": _start_job(job)})

    # -------------------------------------------------------------- скачать

    @app.route("/download/<tok>/<name>")
    @require
    def download(name):
        path = uploads_dir / Path(name).name
        if not path.exists():
            return "Файл не найден", 404
        return send_file(path, as_attachment=True, download_name=path.name)

    return app


def run(host="127.0.0.1", port=8765):
    """Запуск только на loopback. Никогда не слушать 0.0.0.0."""
    app = create_app()
    print(f"\n  Local Table Anonymizer запущен (локально: {host}:{port}, без интернета)")
    print(f"  Откройте в браузере: http://{host}:{port}/\n")
    app.run(host=host, port=port, threaded=True, use_reloader=False)
