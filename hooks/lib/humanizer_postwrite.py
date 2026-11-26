"""Разбор для humanizer-postwrite.sh: см. комментарий в шапке того файла.

Edit|Write — файл из tool_input.file_path (.md/.txt/.html/.rst/.docx/.pptx).
Bash — .docx/.pptx/.html, упомянутые в команде или изменённые в cwd за последние 120 с
(так ловятся колоды и документы, собранные скриптом).
Первая слоповая версия сохраняется как база; при следующих записях того же файла
хук сам отдаёт «было/стало» и проверку пропавших чисел и имён.
"""

import hashlib
import json
import os
import re
import sys
import time

DOC_RE = re.compile(r"\.(md|txt|html?|rst|docx|pptx|pdf)$", re.I)
BIN_RE = re.compile(r"""[^\s"'`=<>|;]+\.(?:pptx|docx|html?|pdf)\b""", re.I)
# Команды, которые собирают документ; тот же список в предфильтре humanizer-postwrite.sh.
BUILD_RE = re.compile(r"pptx|docx|pdf|python|node|npx|claro|soffice|libreoffice|pandoc|marp|typst|weasyprint|make", re.I)
SKIP = (
    "/.claude/",
    "/skills/",
    "/memory/",
    "/handoffs/",
    "/node_modules/",
    "/.git/",
    "/superpowers/",
)
SKIP_NAMES = ("CLAUDE.MD", "AGENTS.MD", "SKILL.MD", "LICENSE.MD", "LICENSE.TXT")
# Текст для модели (бриф агенту, промпт): слоп-счёт к нему не относится, правила —
# prompt-craft references/model-facing-text.md. Признак — имя файла или пометка в начале.
MODEL_NAME_RE = re.compile(r"(-agent|\.prompt|[-_.]system[-_]?prompt)\.(md|txt)$|(^|/)(prompts|agents)/", re.I)
MODEL_MARK_RE = re.compile(r"audience:\s*model", re.I)
# Реплика расшифровки: «[00:12:10] Спикер:» / «Интервьюер:» / «И:» в начале строки.
# Аудит 07.10: 7 из 8 срабатываний — живая речь в расшифровках интервью, не текст модели.
# Спикер повторяется: «Итог:/Риск:/Вывод:» по разу — это документ, не расшифровка.
TURN_RE = re.compile(
    r"^\s*(\[?\d{1,2}:\d{2}(:\d{2})?\]?\s*)?(\*\*)?([А-ЯЁA-Z][\w .ёЁ-]{0,30}?)(\*\*)?:\s"
)


HEAVY_DIRS = {"node_modules", ".git", ".venv", "venv", "__pycache__", ".next", ".cache", "site-packages", "_worktrees", "Library"}
FRESH_EXT = (".pptx", ".docx", ".pdf", ".html")


def fresh_docs(base, now, depth=3, deadline=None):
    """Документы младше 120 с до глубины 3, без тяжёлых каталогов; не дольше 0,4 с на корень."""
    deadline = deadline or time.time() + 0.4
    out = []
    try:
        entries = list(os.scandir(base))
    except OSError:
        return out
    for e in entries:
        if time.time() > deadline:
            break
        try:
            if e.is_file(follow_symlinks=False):
                if e.name.lower().endswith(FRESH_EXT) and now - e.stat().st_mtime < 120:
                    out.append(e.path)
            elif depth and e.is_dir(follow_symlinks=False) and e.name not in HEAVY_DIRS and not e.name.startswith("."):
                out += fresh_docs(e.path, now, depth - 1, deadline)
        except OSError:
            pass
    return out


def is_transcript(text):
    lines = [l for l in text.splitlines() if l.strip()]
    speakers = {}
    for l in lines:
        m = TURN_RE.match(l)
        if m:
            speakers[m.group(4).strip()] = speakers.get(m.group(4).strip(), 0) + 1
    turns = sum(n for n in speakers.values() if n >= 2)
    return turns >= 5 and turns >= 0.3 * len(lines)

try:
    d = json.load(sys.stdin)
    ti = d.get("tool_input") or {}
except Exception:
    sys.exit(0)

now = time.time()
paths = []
named = set()
if ti.get("file_path"):
    paths = [ti["file_path"]]
elif ti.get("command"):
    cmd = ti["command"]
    if not BUILD_RE.search(cmd):
        sys.exit(0)
    cwd = d.get("cwd") or os.getcwd()
    # `cd dir && python build.py deck.pptx`: cwd в событии — каталог сессии, а не тот, куда ушла команда
    bases = [cwd] + [
        os.path.join(cwd, os.path.expanduser(m.strip("\"'")))
        for m in re.findall(r"""(?:^|[;&|]\s*)cd\s+("[^"]+"|'[^']+'|[^\s;&|]+)""", cmd)
    ]
    cand = [os.path.join(b, os.path.expanduser(m)) for b in bases for m in BIN_RE.findall(cmd)]
    # Скрипт часто кладёт результат глубже или в ~/Downloads, не называя путь в команде.
    named = {os.path.normpath(c) for c in cand}
    # ~/Downloads — только если команда его называет: туда же падают файлы из браузера, их текст чужой
    for b in bases + ([os.path.expanduser("~/Downloads")] if "Downloads" in cmd else []):
        cand += fresh_docs(b, now)
    seen = set()
    for c in cand:
        c = os.path.normpath(c)
        if c not in seen and os.path.isfile(c) and now - os.path.getmtime(c) < 120:
            seen.add(c)
            paths.append(c)
    paths = paths[:5]

from_bash = not ti.get("file_path")
if not from_bash:
    named = {os.path.normpath(p) for p in paths}
HARD_LABELS = {"не просто X, а Y", "эксперты считают", "исследования показывают", "по мнению многих"}
blocks = []
sys.path.insert(0, os.environ["HUMANIZER_SCAN"])
cache = os.environ["STAMPS"] + ".d"
out = []

for path in paths:
    base = os.path.basename(path)
    if not DOC_RE.search(path) or base.startswith("~$"):
        continue
    if (
        any(m in path for m in SKIP)
        or base.upper() in SKIP_NAMES
        or base.upper().startswith("CHANGELOG")
    ):
        continue
    if not os.path.isfile(path) or os.path.getsize(path) > 20_000_000:
        continue

    import slop_scan as S

    try:
        text = S.read(path)
        slides = S.read_slides(path) if path.lower().endswith((".pptx", ".html", ".htm")) else None
    except Exception:
        continue
    if is_transcript(text) or MODEL_NAME_RE.search(path) or MODEL_MARK_RE.search(text[:300]):
        continue
    letters = re.findall(r"[^\W\d_]", text)
    if not letters:
        continue
    key = os.path.join(cache, hashlib.sha1(path.encode()).hexdigest()[:16])
    if len(re.findall(r"[а-яёА-ЯЁ]", text)) / len(letters) < 0.5:
        # английский: только остатки чат-бота и «not X but Y»; слова-штампы на людях не замерены и молчат
        en = [h for h in S.scan_en(text)["markers"] if h["cat"] in ("чатбот", "антитеза")]
        en_state = key + ".en"
        try:
            seen_en = open(en_state, encoding="utf-8").read()
        except OSError:
            seen_en = ""
        if not en:
            if seen_en:
                os.remove(en_state)
            continue
        if seen_en == str(len(en)):
            continue  # те же приметы после правки: не повторяемся
        try:
            os.makedirs(cache, exist_ok=True)
            open(en_state, "w", encoding="utf-8").write(str(len(en)))
        except OSError:
            pass
        out.append(
            f"ℹ️ Локальный хук (PostToolUse): {base}, английский текст, приметы ИИ: "
            + "; ".join(f"строка {h['line']}: [{h['label']}] {h['text'][:50]}" for h in en[:5])
            + ". Фразы чат-бота убери, «not X but Y» замени прямым утверждением. Полная проверка: slop_scan.py --lang en ФАЙЛ. "
            "Если это цитата, скажи строкой и иди дальше."
        )
        continue

    r = S.scan(text, None, slides)
    # PreToolUse-хука на Write/Edit нет (проверено 23.11.2026), поэтому жёсткие маркеры ловим здесь при любой длине
    hard = [h for h in r["markers"] if h["cat"] == "чатбот" or h["label"] in HARD_LABELS]
    # блок только для файла, названного в команде; найденное обходом лишь подсказывается
    if from_bash and hard and os.path.normpath(path) in named:
        blocks.append(
            f"{base}: жёсткие маркеры — "
            + "; ".join(f"[{h['label']}] «{h['text'][:50]}»" for h in hard[:5])
        )
    state = key + ".json"
    try:
        prev = json.load(open(state, encoding="utf-8"))
    except (OSError, ValueError):
        prev = None
    min_words = 40 if slides is not None else 150
    # шапка и шаблонные разделы видны и в короткой записке, поэтому для примет вида порог ниже
    short_layout = r["words"] >= 60 and any(f.startswith("вид:") for f in r["flags"])
    if (
        r["words"] < min_words and not prev and not short_layout and not hard
    ):  # с базой сравниваем и короткий результат правки
        continue

    def is_dirty(x):
        chat_ = [h for h in x["markers"] if h["cat"] == "чатбот" or h["label"] in HARD_LABELS]
        slide_bad_ = slides is not None and any(
            "заголовки-темы" in f or "триады" in f for f in x["flags"]
        )
        # ритм — единственный признак, уверенно отделивший модель от человека (compare_model.py, 21.09.2026)
        # от 20 предложений: на коротких новостях флаг ложно срабатывал у 18–33% людей
        flat_ = x["sentences"] >= 20 and any("нет коротких предложений" in f for f in x["flags"])
        # обрубки без глагола и сокращения: сканер их не штрафует заметно, но читатель-новичок не разворачивает (автор, 12.10.2026)
        telegraph_ = any(f.startswith(("обрубки", "сокращения")) for f in x["flags"])
        # любое тире в записанном тексте: решение автора 21.11.2026, жанр его не оправдывает
        dash_ = any(f.startswith("тире") for f in x["flags"])
        # любой «, а не» в записанном тексте: решение автора 23.11.2026, по образцу тире
        dash_ = dash_ or any(h["label"] == S.REVERSE_LABEL for h in x["markers"])
        # вид документа (шапка, шаблонные разделы, строки-ярлыки): по нему читатели узнают ИИ до чтения (21.11.2026)
        layout_ = any(f.startswith("вид:") for f in x["flags"])
        return bool(x["score"] < 80 or x["clusters"] or chat_ or slide_bad_ or flat_ or telegraph_ or dash_ or layout_)

    dirty = is_dirty(r)
    # Авто-жанр: без --genre научный текст ЧЕЛОВЕКА даёт кластер в 55% случаев (замер 21.09.2026,
    # research/calibrate.py). Пробуем только откалиброванные на людях жанры; legal замера не имеет.
    soft = None
    # `--genre tech` глушит плотность заголовков и строки-ярлыки: без этой оговорки авто-жанр оправдал бы ими любой документ
    if dirty and slides is None and not any(f.startswith("вид:") for f in r["flags"]):
        for g in ("science", "tech", "news", "business"):
            rg = S.scan(text, g)
            # жанр news глушит флаг ритма — ровный ритм жанром не оправдываем
            if not is_dirty(rg) and not (r["sentences"] >= 20 and any("нет коротких предложений" in f for f in r["flags"])):
                soft = f"без жанра маркеров {len(r['markers'])}, с `--genre {g}` чисто (счёт {rg['score']})"
                r, dirty = rg, False
                break
    chat = [h for h in r["markers"] if h["cat"] == "чатбот" or h["label"] in HARD_LABELS]

    sig =[len(r["markers"]), r["score"], len(r["flags"])]

    if prev and now - prev["t"] < 6 * 3600:
        if prev["sig"] == sig:
            continue  # ничего не поменялось — молчим
        if prev.get("soft") and not dirty:
            json.dump(
                {"t": prev["t"], "sig": sig, "soft": True},
                open(state, "w", encoding="utf-8"),
            )
            continue  # жанровый текст остался чистым — молчим
        before = open(key + ".txt", encoding="utf-8").read()
        lost = S.fact_check(before, text)
        line = (
            f"ℹ️ Локальный хук (PostToolUse): {base} — маркеров было {prev['sig'][0]}, стало {sig[0]}; "
            f"счёт {prev['sig'][1]} → {sig[1]}; "
            + (
                "; ".join("ВНИМАНИЕ: " + m for m in lost)
                if lost
                else "числа и имена на месте"
            )
            + "."
        )
        if dirty:
            left = (
                sorted({h["label"] for h in r["markers"]})[:6]
                + [f.split(". ")[0] for f in r["flags"] if slides is not None or f.startswith(("вид:", "тире"))][:3]
            )
            line += " Осталось: " + ", ".join(left) + "."
        out.append(line)
        if dirty:
            json.dump({"t": prev["t"], "sig": sig}, open(state, "w", encoding="utf-8"))
        else:
            for f in (state, key + ".txt"):
                try:
                    os.remove(f)
                except OSError:
                    pass
        continue

    if not dirty and not soft:
        continue
    try:
        os.makedirs(cache, exist_ok=True)
        open(key + ".txt", "w", encoding="utf-8").write(text)
        json.dump(
            {"t": now, "sig": sig, "soft": bool(soft)},
            open(state, "w", encoding="utf-8"),
        )
    except OSError:
        pass
    if soft:
        out.append(
            f"ℹ️ Локальный хук (PostToolUse): {base} — {soft}. Похоже на жанровый текст, канцелярит в нём норма; "
            "править не нужно. Если жанр другой — slop_scan.py ФАЙЛ без --genre."
        )
        continue

    lines = [
        f"ℹ️ Локальный хук (PostToolUse): слоп-скан {base} — счёт {r['score']}/100, маркеров {len(r['markers'])}, слов {r['words']}."
    ]
    for c in r["clusters"][:3]:
        lines.append(
            f"  кластер, строка {c['line']}: {c['count']} — {', '.join(c['labels'][:4])}"
        )
    for h in (chat or r["markers"])[:4]:
        lines.append(f"  строка {h['line']}: [{h['cat']}] {h['text'][:50]}")
    shown = [f for f in r["flags"] if f.startswith("вид:")] + [f for f in r["flags"] if not f.startswith("вид:")]
    lines += ["  " + f for f in shown if slides is not None or "нет коротких" in f or f.startswith(("вид:", "тире"))][:5]
    lines.append(
        "Править по ~/.claude/skills/humanizer-ru/SKILL.md (сначала кластеры); после правки хук сам покажет «было/стало» и пропавшие факты. "
        "Договор, закон, техдок — `--genre legal|tech`. Сопоставление по регуляркам, бывает мимо: если это цитата или голос автора, скажи строкой и иди дальше."
    )
    out.append("\n".join(lines))

if blocks:
    print(
        json.dumps(
            {
                "decision": "block",
                "reason": "ℹ️ Локальный хук (PostToolUse humanizer-postwrite): "
                + " | ".join(blocks)
                + ". Исправь текст в исходнике и пересобери файл: чатбот-фразы удалить, «не просто X, а Y» — "
                "утвердить Y напрямую, безымянную атрибуцию — назвать источник или удалить. Цитату возьми в «ёлочки».",
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": "\n\n".join(out),
                },
            },
            ensure_ascii=False,
        )
    )
elif out:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": "\n\n".join(out),
                }
            },
            ensure_ascii=False,
        )
    )
