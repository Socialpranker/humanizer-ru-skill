"""Разбор для humanizer-outbound.sh (PreToolUse): см. комментарий в шапке того файла.

Достаёт текст, который вызов отправит наружу, гонит его через slop_scan.py и отклоняет
вызов при жёстком признаке. Повтор того же текста в течение часа пропускает: так проходит
цитата или текст, который продиктовал пользователь.
"""

import hashlib
import json
import os
import re
import shlex
import sys
import time

TEXT_KEYS = {"body", "text", "content", "message", "markdown", "new_text", "html", "html_body",
             "htmlBody", "comment", "description", "notes", "note", "payload"}
DOC_EXT = re.compile(r"\.(md|txt|html?|rst|docx|pptx|pdf)$", re.I)
GH_WRITE = re.compile(r"\bgh\s+(?:(?:pr|issue|release)\s+(?:create|comment|edit|review)|api)\b")
# Набор текста в браузере: короче этого обычно поисковый запрос или поле формы, а не публикация.
BROWSER_MIN_WORDS = 25
MIN_WORDS = 8
# Признаки, которые правятся с одного попадания (patterns.md: «всегда», раздел 15 и метки раздела 14
# с нулём у людей). Безымянная «принято считать / как известно» и «ряд источников» не входят:
# у людей в технических и научных текстах они обычны.
HARD_CATS = {"чатбот", "антитеза"}
HARD_LABELS = {
    "эксперты считают", "исследования показывают", "по мнению многих",
    "догадка на пустом месте: сведений нет в открытом доступе",
    "спор с никем: не поймите неправильно", "текст о документе: таблица ниже сравнивает",
    "разгон: штука в том, что", "афоризм: язык доверия / настоящий вопрос",
    "слова через точку: каждый. божий. день.", "ударные концовки",
    "«Это важно.» отдельной фразой", "честный ответ / правда в том", "Вот в чём дело:", "подвох в том",
    "тихо меняет", "Спойлер:/Если коротко:", "решение рождается", "служит напоминанием",
    "зачин с двоеточием: Итог:/Вывод:", "заголовок «Ключевые выводы»", "ровно как усилитель",
    "подводка-анонс: Причин две. / Вывод простой:",
}
HARD_FLAGS = ("тире", "значки вместо слов", "AI words")
# Вид документа читатель замечает первым (решение автора 21.11.2026). В письме, сообщении, документе и
# артефакте шапка и шаблонные разделы отклоняются; в тексте PR, issue и релиза заголовки приняты.
LAYOUT_FLAGS = ("вид: шапка", "вид: шаблонные разделы")


def collect(node, key=None, out=None):
    out = [] if out is None else out
    if isinstance(node, dict):
        for k, v in node.items():
            collect(v, k, out)
    elif isinstance(node, list):
        for v in node:
            collect(v, key, out)
    elif isinstance(node, str) and key in TEXT_KEYS:
        out.append(node)
    return out


def gh_texts(cmd):
    texts = [m.group(2) for m in re.finditer(r"<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n(.*?)\n\s*\1\b", cmd, re.S)]
    if texts:
        return texts
    try:
        argv = shlex.split(cmd)
    except ValueError:
        return []
    for i, a in enumerate(argv[:-1]):
        nxt = argv[i + 1]
        if a in ("--body", "-b", "--notes", "-n"):
            texts.append(nxt)
        elif a in ("--body-file", "--notes-file") or (a == "-F" and "api" not in argv[:3]):
            if nxt != "-" and os.path.isfile(os.path.expanduser(nxt)):
                texts.append(open(os.path.expanduser(nxt), encoding="utf-8", errors="replace").read())
        elif a in ("-f", "-F", "--field", "--raw-field") and nxt.startswith("body="):
            val = nxt[5:]
            if val.startswith("@") and os.path.isfile(os.path.expanduser(val[1:])):
                val = open(os.path.expanduser(val[1:]), encoding="utf-8", errors="replace").read()
            texts.append(val)
    for a in argv:
        for pre in ("--body=", "--notes="):
            if a.startswith(pre):
                texts.append(a[len(pre):])
    return texts


def browser_texts(name, ti):
    acts = []
    if name.endswith("__computer") or name.endswith("__form_input"):
        acts = [ti]
    elif name.endswith("__browser_batch"):
        acts = [a.get("input") or {} for a in ti.get("actions") or [] if a.get("name") in ("computer", "form_input")]
    out = []
    for a in acts:
        val = a.get("text") if a.get("action") == "type" else a.get("value")
        if isinstance(val, str):
            out.append(val)
    return out


def extract(d, S):
    name = d.get("tool_name") or ""
    ti = d.get("tool_input") or {}
    if name == "Bash":
        cmd = ti.get("command") or ""
        return (gh_texts(cmd) if GH_WRITE.search(cmd) else []), 0, False
    if "claude-in-chrome" in name or "Claude_Browser" in name:
        return browser_texts(name, ti), BROWSER_MIN_WORDS, True
    texts = collect(ti)
    for f in ti.get("files") or []:
        p = (f or {}).get("path") or ""
        if DOC_EXT.search(p) and os.path.isfile(p):
            try:
                texts.append(S.read(p))
            except Exception:
                pass
    return texts, 0, True


def plain(t, S):
    if re.search(r"<(?:p|div|h[1-6]|li|section|span|br|body|html)\b", t, re.I):
        return S._html_text(t)
    return t


def lang_of(t):
    letters = re.findall(r"[^\W\d_]", t)
    if not letters:
        return None
    cyr = len(re.findall(r"[а-яёА-ЯЁ]", t)) / len(letters)
    lat = len(re.findall(r"[a-zA-Z]", t)) / len(letters)
    return "ru" if cyr >= 0.5 else "en" if lat >= 0.8 else None


def problems(text, S, layout=False):
    lang = lang_of(text)
    if lang == "ru":
        r = S.scan(text)
        hits = [h for h in r["markers"] if h["cat"] in HARD_CATS or h["label"] in HARD_LABELS]
    elif lang == "en":
        r = S.scan_en(text)
        hits = r["markers"]
    else:
        return 0, []
    found = [f"[{h['label']}] «{h['text'][:60]}»" for h in hits[:6]]
    found += [f.split(". ")[0] for f in r["flags"] if f.startswith(HARD_FLAGS + (LAYOUT_FLAGS if layout else ()))]
    return r["words"], found


def main():
    try:
        d = json.load(sys.stdin)
    except ValueError:
        return
    sys.path.insert(0, os.environ["HUMANIZER_SCAN"])
    import slop_scan as S

    texts, min_words, layout = extract(d, S)
    texts = [plain(t, S) for t in texts if t and t.strip()]
    report = []
    for t in texts:
        words, found = problems(t, S, layout)
        if words >= max(MIN_WORDS, min_words):
            report += found
    if not report:
        return
    stamps = os.environ["STAMPS"]
    key = hashlib.sha1("\n\x00".join(texts).encode()).hexdigest()[:20]
    stamp = os.path.join(stamps, key)
    if os.path.exists(stamp) and time.time() - os.path.getmtime(stamp) < 3600:
        # тот же текст второй раз: автор решил оставить. Пропуск пишется в журнал, чтобы пользователь мог его проверить
        try:
            with open(os.path.join(stamps, "passed.log"), "a", encoding="utf-8") as log:
                log.write(f"{time.strftime('%Y-%m-%d %H:%M')}\t{d.get('tool_name') or ''}\t{'; '.join(report)[:300]}\n")
        except OSError:
            pass
        return
    try:
        os.makedirs(stamps, exist_ok=True)
        open(stamp, "w").close()
    except OSError:
        pass
    reason = (
        "ℹ️ Локальный хук humanizer-outbound (PreToolUse): текст уходит наружу, а в нём "
        + "; ".join(report)
        + ". Исправь по ~/.claude/skills/humanizer-ru (шапка и разделы: generation.md, правила 1–4; "
        "тире: patterns.md раздел 10, подача и концовки: раздел 15, "
        "чатбот-фразы удалить, «не просто X, а Y» заменить прямым утверждением) и отправь снова. "
        "Если текст продиктовал пользователь или это цитата, отправь тот же текст без изменений: повтор хук пропустит; "
        "Пользователю скажи одной строкой, что оставил и почему."
    )
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": reason}}, ensure_ascii=False))


try:
    main()
except Exception:
    pass
