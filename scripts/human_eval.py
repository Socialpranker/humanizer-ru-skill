#!/usr/bin/env python3
"""Оценка «человечности» текста без живых читателей: сравнение с текстами людей того же жанра.

  human_eval.py profile --human ЭТАЛОН [--human ...] ТЕКСТ [ТЕКСТ ...]
      манера текста против разброса у людей: какие замеры выходят за пределы 10–90% эталона
  human_eval.py pack --out ПАПКА --human ЭТАЛОН --control 'GLOB' --set ИМЯ='GLOB' [--set ...]
      слепая пачка для судьи: люди, заведомо модельные тексты (контроль) и проверяемые наборы
  human_eval.py score ПАПКА ВЕРДИКТ.json [ВЕРДИКТ2.json ...]
      сила каждого судьи на контроле и доля проверяемых текстов, которые он принял за модель

ЭТАЛОН: файл .jsonl с полем text или шаблон путей к текстовым файлам. Основание и замеры: references/evaluation.md.
"""
import argparse
import glob
import json
import os
import random
import re
import statistics
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import slop_scan as S  # noqa: E402

W = re.compile(r"[А-Яа-яЁёA-Za-z0-9]+(?:-[А-Яа-яЁёA-Za-z0-9]+)*")


def _rx(words):
    return re.compile(r"(?<![\w-])(?:" + "|".join(words) + r")(?![\w-])", re.I)


NOMINAL = re.compile(r"\w{3,}(?:ани|ени|аци|яци|ост|ств)(?:е|я|ю|ем|и|й|ях|ями|ям|ей|ь|ью|о|а|у|ом|ах|ами|ам)$", re.I)
PARTIC = re.compile(
    r"\w{3,}(?:ущ|ющ|ащ|ящ|вш|енн|анн|янн)(?:ий|ая|ое|ие|его|ей|ему|ую|им|ими|их|ые|ый|ого|ому|ым|ыми|ых|ой)(?:ся)?$", re.I
)
PARTICLES = _rx("же ведь вот уж ли бы даже просто вообще вс[её]-таки тоже ещ[её] лишь именно разве хоть".split())
PRON1 = _rx("я мы мне меня мной нас нам нами мой моя мо[её] мои наш наша наше наши нашего нашей наших нашим".split())
HEDGE = _rx("возможно вероятно пожалуй кажется по-видимому видимо наверное скорее\\s+всего похоже вроде может\\s+быть".split())
AMPL = _rx("очень крайне чрезвычайно абсолютно безусловно совершенно гораздо намного весьма слишком сильно совсем".split())
CONJ_START = re.compile(r"^(?:И|А|Но|Да|Ну|Или|Зато)\s")

# имя: (как называть в отчёте, группа). Группа «конкретика» зависит от материала, а не от манеры письма.
FEATURES = {
    "sent_mean": ("средняя длина предложения, слов", "ритм"),
    "sent_cv": ("разброс длины предложений (отклонение к средней)", "ритм"),
    "sent_adjdiff": ("перепад длины соседних предложений", "ритм"),
    "sent_short": ("доля предложений до 6 слов", "ритм"),
    "sent_long": ("доля предложений от 25 слов", "ритм"),
    "word_len": ("средняя длина слова, букв", "слова"),
    "long_words": ("доля слов от 10 букв", "слова"),
    "nominal": ("доля отглагольных и отвлечённых существительных", "слова"),
    "partic": ("доля причастий", "слова"),
    "mattr": ("разнообразие слов в окне 50", "слова"),
    "bigram_rep": ("доля повторённых пар слов", "слова"),
    "particles": ("частицы на 100 слов", "слова"),
    "pron1": ("«я» и «мы» на 100 слов", "слова"),
    "hedge": ("слова сомнения на 100 слов", "слова"),
    "ampl": ("усилители на 100 слов", "слова"),
    "conj_start": ("доля предложений с «И», «А», «Но» в начале", "ритм"),
    "comma": ("запятые на 100 слов", "знаки"),
    "colon": ("двоеточия на 100 слов", "знаки"),
    # тире здесь нет намеренно: в своём тексте его не ставят (generation.md, правило 7), и недобор к людям не изъян
    "paren": ("скобки на 100 слов", "знаки"),
    "qmark": ("вопросы на предложение", "знаки"),
    "zlib": ("сжимаемость первых 1500 знаков", "слова"),
    "digits": ("доля слов с цифрами", "конкретика"),
    "names": ("имена собственные на 100 слов", "конкретика"),
    "quote": ("кавычки на 100 слов", "конкретика"),
}


def features(text):
    """Замеры манеры по самому тексту, без морфологии и без модели. None, если текст короче 60 слов."""
    text = text.replace(" ", " ")
    sents = [s for s in S.split_sentences(text) if len(W.findall(s)) >= 2]
    words = W.findall(text)
    n = len(words)
    if n < 60 or len(sents) < 4:
        return None
    lw = [w.lower() for w in words]
    sl = [len(W.findall(s)) for s in sents]
    m = statistics.mean(sl)
    per = lambda c: 100.0 * c / n  # noqa: E731
    bg = list(zip(lw, lw[1:]))
    raw = text[:1500].encode("utf-8")
    return {
        "sent_mean": m,
        "sent_cv": statistics.pstdev(sl) / m,
        "sent_adjdiff": statistics.mean(abs(a - b) for a, b in zip(sl, sl[1:])) / m,
        "sent_short": sum(x <= 6 for x in sl) / len(sl),
        "sent_long": sum(x >= 25 for x in sl) / len(sl),
        "word_len": statistics.mean(len(w) for w in words),
        "long_words": sum(len(w) >= 10 for w in words) / n,
        "nominal": sum(bool(NOMINAL.match(w)) for w in words) / n,
        "partic": sum(bool(PARTIC.match(w)) for w in words) / n,
        "mattr": statistics.mean(len(set(lw[i : i + 50])) / 50 for i in range(0, max(1, n - 50), 5)),
        "bigram_rep": 1 - len(set(bg)) / len(bg),
        "particles": per(len(PARTICLES.findall(text))),
        "pron1": per(len(PRON1.findall(text))),
        "hedge": per(len(HEDGE.findall(text))),
        "ampl": per(len(AMPL.findall(text))),
        "conj_start": sum(bool(CONJ_START.match(s.strip())) for s in sents) / len(sents),
        "comma": per(text.count(",")),
        "colon": per(text.count(":")),
        "paren": per(text.count("(")),
        "qmark": text.count("?") / len(sl),
        "zlib": len(zlib.compress(raw, 9)) / len(raw),
        "digits": sum(any(ch.isdigit() for ch in w) for w in words) / n,
        "names": per(len(S.NAME.findall(text))),
        "quote": per(text.count("«") + text.count('"')),
    }


# Абзацы считаются по тексту с переносами строк: plain() их склеивает, поэтому замеры идут отдельно от FEATURES.
PAR_FEATURES = {
    "par_cv": ("разброс длины абзацев (отклонение к средней)", "абзацы"),
    "par_per100": ("абзацев на 100 слов", "абзацы"),
}


def par_features(text, words=0):
    """Замеры абзацев. Заголовки и пункты списков абзацами не считаются. None, если абзацев меньше трёх."""
    text = re.sub(r"^\s*#{1,6}\s+.*$", "", text, flags=re.M)
    text = re.sub(r"^[ \t]*[^\n]{1,110}[^\n.!?…,;:\s][ \t]*\n(?=[ \t]*\n)", "", text, flags=re.M)
    text = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+.*$", "", text, flags=re.M)
    sizes = []
    for par in re.split(r"\n+", text):
        k = len(W.findall(par))
        if not k:
            continue
        if words and sizes and sum(sizes) + k > words:
            break
        sizes.append(k)
    if len(sizes) < 3:
        return None
    m = statistics.mean(sizes)
    return {"par_cv": statistics.pstdev(sizes) / m, "par_per100": 100.0 * len(sizes) / sum(sizes)}


def plain(text, words=0):
    """Текст без разметки, одним абзацем; при words обрезан по границе предложения."""
    text = re.sub(r"^\s*#{1,6}\s+.*$", "", text, flags=re.M)
    # строка-заголовок без разметки: короткая, без точки в конце; иначе она склеится с первым предложением
    text = re.sub(r"^[ \t]*[^\n]{1,110}[^\n.!?…,;:\s][ \t]*\n(?=[ \t]*\n)", "", text, flags=re.M)
    text = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+", "", text, flags=re.M)
    text = re.sub(r"\*\*|__|`", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not words:
        return text
    out, n = [], 0
    for s in S.split_sentences(text):
        k = len(W.findall(s))
        if out and n + k > words:
            break
        out.append(s.strip())
        n += k
    return " ".join(out)


def topic(text):
    """Опорные слова темы: длинные слова по первым шести буквам и числа."""
    return {w[:6] for w in (x.lower() for x in W.findall(text)) if len(w) >= 7 or w.isdigit()}


def same_topic(a, b):
    """Два отрывка об одном и том же: судья узнал бы модель по повтору темы, а не по манере."""
    return len(a & b) / max(1, min(len(a), len(b))) >= 0.3


def load(spec):
    """Тексты из .jsonl (поле text) или по шаблону путей. Возвращает [(источник, текст)]."""
    spec = os.path.expanduser(spec)
    if spec.endswith(".jsonl"):
        with open(spec, encoding="utf-8") as fh:
            return [(f"{spec}:{i}", json.loads(line)["text"]) for i, line in enumerate(fh, 1) if line.strip()]
    paths = sorted(glob.glob(spec, recursive=True)) if not os.path.isfile(spec) else [spec]
    if not paths:
        sys.exit(f"Нет файлов по пути: {spec}")
    return [(p, str(S.read(p))) for p in paths]


def _write(path, body):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)


def _json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def auroc(pos, neg):
    """Вероятность, что случайное значение из pos больше случайного из neg (ничья считается за половину)."""
    if not pos or not neg:
        return float("nan")
    wins = sum((a > b) + 0.5 * (a == b) for a in pos for b in neg)
    return wins / (len(pos) * len(neg))


def quantile(xs, q):
    xs = sorted(xs)
    i = q * (len(xs) - 1)
    lo = int(i)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)


def profile(texts, human, words=0):
    """Сравнивает манеру текстов с эталоном людей. Эталон режется до длины проверяемых текстов."""
    cand = [f for f in (features(plain(t)) for _, t in texts) if f]
    if not cand:
        return {"error": "в проверяемых текстах меньше 60 слов"}
    target = words or int(statistics.median(len(W.findall(plain(t))) for _, t in texts))
    ref = [f for f in (features(plain(t, target)) for _, t in human) if f]
    if len(ref) < 20:
        return {"error": f"в эталоне {len(ref)} текстов от 60 слов, для разброса нужно не меньше 20"}
    def row(k, label, group, c, h):
        lo, hi = quantile(h, 0.1), quantile(h, 0.9)
        med = statistics.median(c)
        a = auroc(c, h)
        # набор от 8 текстов сравнивается попарно: его медиана может лежать внутри разброса людей
        out = (a >= 0.8 or a <= 0.2) if len(c) >= 8 else (med < lo or med > hi)
        return {"key": k, "label": label, "group": group, "text": med, "lo": lo, "hi": hi, "auroc": a, "out": out, "n": len(c)}

    rows = [row(k, label, group, [f[k] for f in cand], [f[k] for f in ref]) for k, (label, group) in FEATURES.items()]
    pc = [f for f in (par_features(t) for _, t in texts) if f]
    pr = [f for f in (par_features(t, target) for _, t in human) if f]
    par_note = ""
    if not pc:
        par_note = "в проверяемых текстах меньше трёх абзацев"
    elif len(pr) < 20:
        par_note = f"в эталоне {len(pr)} текстов с тремя абзацами, нужно не меньше 20"
    else:
        rows += [row(k, label, group, [f[k] for f in pc], [f[k] for f in pr]) for k, (label, group) in PAR_FEATURES.items()]
    return {"n": len(cand), "ref": len(ref), "words": target, "rows": rows, "par_note": par_note}


def profile_report(r):
    if "error" in r:
        return "Сравнить не с чем: " + r["error"] + "."
    out = [f"Манера против эталона: текстов {r['n']}, людей в эталоне {r['ref']}, длина окна {r['words']} слов."]
    bad = [x for x in r["rows"] if x["out"]]
    style = [x for x in bad if x["group"] != "конкретика"]
    out.append(f"За пределами людей: {len(style)} из {sum(x['group'] != 'конкретика' for x in r['rows'])} замеров манеры.")
    for x in bad:
        note = " (зависит от материала)" if x["group"] == "конкретика" else ""
        if x["n"] >= 8:
            side = "выше" if x["auroc"] >= 0.8 else "ниже"
            pairs = max(x["auroc"], 1 - x["auroc"])
            out.append(f"  {x['label']}: медиана {x['text']:.3g}, {side}, чем у людей, в {pairs:.0%} пар (у людей {x['lo']:.3g}–{x['hi']:.3g}){note}")
        else:
            side = "выше" if x["text"] > x["hi"] else "ниже"
            out.append(f"  {x['label']}: {x['text']:.3g}, {side}, чем у людей ({x['lo']:.3g}–{x['hi']:.3g}){note}")
    if r["par_note"]:
        out.append(f"Абзацы не сравнивались: {r['par_note']}.")
    out.append("Это замер сходства с эталоном, а не цель правки: подгонка под числа даёт текст хуже прежнего.")
    return "\n".join(out)


BRIEF = """Цель: оценить, отличит ли внимательный читатель тексты языковой модели от текстов людей. Результат нужен для проверки правил письма, поэтому честная оценка важнее уверенного тона.

В файле {pack} лежат {n} отрывков на русском языке, каждый под своим номером. Часть написали люди, часть языковая модель; сколько каких, неизвестно. Все отрывки очищены от разметки, слиты в один абзац и обрезаны до одной длины, поэтому заголовки, абзацы и обрыв в конце ничего не говорят об авторе. Тема и время события тоже ничего не говорят: модели писали на темы человеческих текстов.

По каждому отрывку реши, кто его написал, и оцени вероятность того, что это модель, числом от 0 до 100. Оценивай каждый отрывок сам по себе: не выравнивай доли и не возвращайся к уже оценённым. Назови одну примету, на которую опираешься, и приведи её словами из отрывка.

Прочитай файл целиком через Read. Другие файлы не читай, Bash и поиск не запускай, субагентов не запускай. Результат запиши через Write в файл {verdict} в виде JSON: {{"T01": {{"p": 85, "cue": "примета и слова из текста"}}, "T02": ...}}, по одной записи на каждый номер. В ответе верни одну строку: сколько отрывков оценено."""


def pack(out, human, control, sets, per=12, words=250, seed=1):
    rnd = random.Random(seed)
    items = []
    topics = []  # в пачке одна тема встречается один раз

    def take(kind, name, pairs, limit):
        pairs = [(src, plain(t, words)) for src, t in pairs]
        pairs = [(src, t) for src, t in pairs if len(W.findall(t)) >= 60]
        rnd.shuffle(pairs)
        got = 0
        for src, t in pairs:
            tp = topic(t)
            if got == limit or any(same_topic(tp, o) for o in topics):
                continue
            topics.append(tp)
            items.append({"kind": kind, "set": name, "src": src, "text": t})
            got += 1

    n_sets = 0
    for name, spec in sets:
        take("candidate", name, load(spec), per)
        n_sets += 1
    take("control", "контроль", [p for spec in control for p in load(spec)], per)
    take("human", "люди", [p for spec in human for p in load(spec)], max(per, per * (n_sets + 1) // 2))
    rnd.shuffle(items)
    os.makedirs(out, exist_ok=True)
    key = {}
    lines = []
    for i, it in enumerate(items, 1):
        tid = f"T{i:02d}"
        key[tid] = {k: it[k] for k in ("kind", "set", "src")}
        lines.append(f"[{tid}]\n{it['text']}\n")
    packp = os.path.join(out, "pack.text")
    _write(packp, "\n".join(lines))
    _write(os.path.join(out, "key.json"), json.dumps(key, ensure_ascii=False, indent=1))
    brief = BRIEF.format(pack=os.path.abspath(packp), n=len(items), verdict=os.path.abspath(os.path.join(out, "verdict_ИМЯ.json")))
    _write(os.path.join(out, "brief.text"), brief)
    return key


def score(folder, verdict_paths, seed=1, boots=2000):
    key = _json(os.path.join(folder, "key.json"))
    judges = [_json(p) for p in verdict_paths]
    p = {}
    for tid in key:
        vals = [float(j[tid]["p"]) for j in judges if tid in j]
        if vals:
            p[tid] = statistics.mean(vals)
    by = {}
    for tid, k in key.items():
        if tid in p:
            by.setdefault((k["kind"], k["set"]), []).append(tid)
    hum = [p[t] for t in by.get(("human", "люди"), [])]
    rnd = random.Random(seed)

    def ci(pos):
        if len(pos) < 2 or len(hum) < 2:
            return (float("nan"), float("nan"))
        vals = sorted(auroc(rnd.choices(pos, k=len(pos)), rnd.choices(hum, k=len(hum))) for _ in range(boots))
        return vals[int(0.025 * boots)], vals[int(0.975 * boots)]

    res = {"judges": len(judges), "human_n": len(hum), "fpr": sum(v > 50 for v in hum) / max(1, len(hum)), "sets": []}
    for (kind, name), tids in sorted(by.items()):
        if kind == "human":
            continue
        pos = [p[t] for t in tids]
        lo, hi = ci(pos)
        top = sorted(tids, key=lambda t: -p[t])[: max(3, len(tids) // 3)]  # приметы самых подозрительных отрывков набора
        cues = [f"{t} ({float(j[t]['p']):.0f}): {j[t].get('cue', '')}" for t in top for j in judges if t in j]
        res["sets"].append(
            {"kind": kind, "set": name, "n": len(pos), "flagged": sum(v > 50 for v in pos) / len(pos), "auroc": auroc(pos, hum), "lo": lo, "hi": hi, "cues": cues}
        )
    if len(judges) > 1:
        both = [t for t in key if all(t in j for j in judges)]
        res["agree"] = sum(len({float(j[t]["p"]) > 50 for j in judges}) == 1 for t in both) / max(1, len(both))
    ctrl = [s for s in res["sets"] if s["kind"] == "control"]
    res["power"] = ctrl[0]["auroc"] if ctrl else float("nan")
    return res


def score_report(r):
    out = [f"Людей в пачке: {r['human_n']}, из них принято за модель {r['fpr']:.0%}."]
    valid = r["power"] == r["power"] and r["power"] >= 0.75
    if not valid:
        out.append(f"Контроль не пройден: заведомо модельные тексты судья отличает от людей с AUROC {r['power']:.2f} (нужно от 0,75). Вердикты по наборам ниже ничего не значат.")
    for s in r["sets"]:
        name = "контроль (заведомо модель)" if s["kind"] == "control" else s["set"]
        line = f"  {name}: n={s['n']}, принято за модель {s['flagged']:.0%}, AUROC против людей {s['auroc']:.2f} (95%: {s['lo']:.2f}–{s['hi']:.2f})"
        if s["kind"] == "candidate" and valid:
            if not s["lo"] > 0.5:
                line += ". Судья набор от людей не отличил"
            elif s["flagged"] > r["fpr"]:
                line += ". Судья отличает набор от людей"
            else:
                line += ". Вердикт «модель» судья не выносит, но оценки набора выше, чем у людей: остаточные приметы есть"
        out.append(line)
    for s in r["sets"]:
        if s["kind"] == "candidate" and s["cues"]:
            out.append(f"Приметы, названные в наборе «{s['set']}»:")
            out.extend(f"  {c}" for c in s["cues"][:8])
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("profile")
    a.add_argument("texts", nargs="+")
    a.add_argument("--human", action="append", required=True)
    a = sub.add_parser("pack")
    a.add_argument("--out", required=True)
    a.add_argument("--human", action="append", required=True)
    a.add_argument("--control", action="append", required=True)
    a.add_argument("--set", action="append", required=True, metavar="ИМЯ=GLOB")
    a.add_argument("--per", type=int, default=12)
    a.add_argument("--words", type=int, default=250)
    a.add_argument("--seed", type=int, default=1)
    a = sub.add_parser("score")
    a.add_argument("folder")
    a.add_argument("verdicts", nargs="+")
    args = ap.parse_args(argv)
    if args.cmd == "profile":
        texts = [p for spec in args.texts for p in load(spec)]
        human = [p for spec in args.human for p in load(spec)]
        print(profile_report(profile(texts, human)))
    elif args.cmd == "pack":
        key = pack(args.out, args.human, args.control, [s.split("=", 1) for s in args.set], args.per, args.words, args.seed)
        kinds = [k["kind"] for k in key.values()]
        print(f"Пачка: {len(key)} отрывков (людей {kinds.count('human')}, контроль {kinds.count('control')}, проверяемых {kinds.count('candidate')}). Задание судье: {os.path.join(args.out, 'brief.text')}")
    else:
        # каждый судья считается отдельно: в проверке 21.11.2026 средняя двух судей спрятала находку сильного за слабым
        for v in args.verdicts:
            if len(args.verdicts) > 1:
                print(f"Судья {os.path.basename(v)}")
            print(score_report(score(args.folder, [v])))
        if len(args.verdicts) > 1:
            print(f"Судьи сошлись в вердикте на {score(args.folder, args.verdicts)['agree']:.0%} отрывков. Вывод бери по самому строгому судье, прошедшему контроль.")


if __name__ == "__main__":
    main()
