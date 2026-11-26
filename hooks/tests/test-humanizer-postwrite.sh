#!/bin/bash
# Регрессия для hooks/humanizer-postwrite.sh (PostToolUse, слоп-скан документов).
# Как в test-skill-trigger-injector.sh: каждый «молчит» имеет парный «срабатывает» на
# том же файле с одним отличием — иначе тишина может быть следствием поломки.
# Мутация: HUMANIZER_SCAN=/пустая/папка bash test-...sh — тест обязан покраснеть.
#
# Запуск:  bash hooks/tests/test-humanizer-postwrite.sh

HOOK="${HOOK:-$(cd "$(dirname "$0")/.." && pwd)/humanizer-postwrite.sh}"
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
export HOOKLOG_FILE="$W/hooks.log"
export HUMANIZER_STAMPS="$W/stamps"
pass=0; fail=0; failed=()

# ≥150 слов слопа: 30 повторов фразы с кластером маркеров
python3 - "$W" <<'PY'
import sys,os
w=sys.argv[1]
bad=("В современном мире автоматизация играет ключевую роль. Данное решение позволяет осуществлять управление. "
     "Это не просто инструмент — это новый способ мышления. Эксперты считают, что подход открывает новые горизонты. ")*7
clean=("Компании автоматизируют рутину, потому что это дешевле. Мы прогнали 40 проектов за два года и нашли четыре типовые ошибки. "
       "Большинство проектов буксуют не из-за технологий, а из-за того, что никто не решил, что именно автоматизировать. ")*3
open(w+"/bad.md","w").write(bad)
open(w+"/clean.md","w").write(clean)
open(w+"/short.md","w").write("Данное решение играет ключевую роль.")
open(w+"/bad_en.md","w").write("Furthermore, this groundbreaking solution plays a pivotal role in the modern landscape. "*20)
open(w+"/bad.py","w").write("# "+bad)
os.makedirs(w+"/.claude/skills/x",exist_ok=True)
open(w+"/.claude/skills/x/bad.md","w").write(bad)
PY

fire() { printf '{"tool_name":"Write","tool_input":{"file_path":"%s"}}' "$1" | bash "$HOOK" 2>&1; }
check() {  # check <fires|silent> <имя> <путь>
  local out ok; rm -f "$HUMANIZER_STAMPS" "$HUMANIZER_STAMPS.d"/* 2>/dev/null
  out=$(fire "$3")
  case "$1" in
    fires)  echo "$out" | grep -q 'слоп-скан' && ok=1 || ok=0 ;;
    silent) [ -z "$out" ] && ok=1 || ok=0 ;;
  esac
  if [ "$ok" = 1 ]; then pass=$((pass+1)); else fail=$((fail+1)); failed+=("$2"); printf '  ✗ %s\n' "$2"; fi
}

check fires  "слоповый русский .md"        "$W/bad.md"
check silent "чистый русский .md"          "$W/clean.md"
check silent "короткий (<150 слов)"        "$W/short.md"
check silent "английский слоп"             "$W/bad_en.md"
check silent "код (.py)"                   "$W/bad.py"
check silent "служебный путь (.claude/skills)" "$W/.claude/skills/x/bad.md"
cp "$W/bad.md" "$W/brief-agent.md"; cp "$W/bad.md" "$W/brief.prompt.md"
{ echo "<!-- audience: model -->"; cat "$W/bad.md"; } > "$W/marked.md"
check silent "текст для модели: *-agent.md"     "$W/brief-agent.md"
check silent "текст для модели: *.prompt.md"    "$W/brief.prompt.md"
check silent "текст для модели: пометка audience" "$W/marked.md"
check silent "файла нет"                   "$W/nope.md"

# короткое письмо (<150 слов): фраза чат-бота видна при любой длине; пара без неё молчит
python3 - "$W" <<'PY'
import sys
w=sys.argv[1]
body=("Тексты программы нам прислали на девять дней позже, поэтому вёрстка началась позже. "
      "В форме оплаты нашли ошибку, подрядчик чинит её до 8 декабря. После этого остаётся неделя на проверку страниц и писем.")
open(w+"/letter.md","w").write(body)
open(w+"/letter_bot.md","w").write("Конечно! Давайте разберёмся, почему запуск переехал.\n\n"+body+"\n\nНадеюсь, это поможет!")
en=("The program copy arrived nine days later than planned, and we found a bug in the payment form. "
    "The contractor is fixing it by December 8, which leaves a week for testing.")
open(w+"/letter_en.md","w").write(en)
open(w+"/letter_en_bot.md","w").write("Certainly! Here is why the launch moved.\n\n"+en+"\n\nI hope this helps!")
PY
check silent "короткое письмо без примет"          "$W/letter.md"
check fires  "короткое письмо с фразой чат-бота"   "$W/letter_bot.md"
check silent "английское письмо без примет"        "$W/letter_en.md"
rm -f "$HUMANIZER_STAMPS.d"/* 2>/dev/null
en_out=$(fire "$W/letter_en_bot.md")
if echo "$en_out" | grep -q 'английский текст' && echo "$en_out" | grep -q 'I hope this helps'; then pass=$((pass+1)); else fail=$((fail+1)); failed+=("английское письмо с фразой чат-бота"); printf '  ✗ %s\n' "английское письмо с фразой чат-бота"; fi
if [ -z "$(fire "$W/letter_en_bot.md")" ]; then pass=$((pass+1)); else fail=$((fail+1)); failed+=("английское: повтор молчит"); printf '  ✗ %s\n' "английское: повтор молчит"; fi

# база и «было/стало»: повтор без изменений тихий; после правки — отчёт с проверкой фактов
reset() { rm -f "$HUMANIZER_STAMPS" "$HUMANIZER_STAMPS.d"/* 2>/dev/null; }
expect() {  # expect <имя> <искомое|-> <вывод>
  local ok; if [ "$2" = "-" ]; then [ -z "$3" ] && ok=1 || ok=0; else echo "$3" | grep -q "$2" && ok=1 || ok=0; fi
  if [ "$ok" = 1 ]; then pass=$((pass+1)); else fail=$((fail+1)); failed+=("$1"); printf '  ✗ %s\n' "$1"; fi
}
reset; fire "$W/bad.md" >/dev/null
expect "повтор без изменений молчит" - "$(fire "$W/bad.md")"
cp "$W/clean.md" "$W/bad.md"
expect "после правки: было/стало" "маркеров было" "$(fire "$W/bad.md")"
expect "после чистой версии база снята" - "$(fire "$W/bad.md")"

# pptx: через Write-путь и через Bash (файл упомянут в команде, свежий mtime)
python3 - "$W" <<'PY'
import sys,zipfile
w=sys.argv[1]
def slide(t,b): return '<p:sld>'+"".join(f"<a:p><a:r><a:t>{x}</a:t></a:r></a:p>" for x in [t]+b)+'</p:sld>'
bad=[("Стратегия",[]),("Результаты",["Скорость работы команды","Качество всех решений","Надёжность нашей платформы"]),("Преимущества",["Гибкость всей системы","Масштабируемость решений","Отказоустойчивость сервисов"]),("Команда",["Большой опыт работы","Глубокая экспертиза рынка","Драйв и вовлечённость"]),("Планы",["Рост всех показателей","Развитие новых продуктов","Выход на рынки"])]
good=[("Стратегия",[]),("Выручка выросла на 12% за год",["Основной вклад дал сегмент корпоративных клиентов","Розница просела на 3% из-за закрытия двух точек"]),("Отток снизился: 8% против 11%",["Помогла новая поддержка и перенос обращений в чат"]),("В 2026 открываем два офиса",["Казань откроется в марте","Минск откроется в сентябре","Бюджет на оба 40 млн","Нанимаем 25 человек"])]
for name,sl in (("deck_bad",bad),("deck_good",good)):
    with zipfile.ZipFile(f"{w}/{name}.pptx","w") as z:
        for i,(t,b) in enumerate(sl,1): z.writestr(f"ppt/slides/slide{i}.xml",slide(t,b))
PY
bash_fire() { printf '{"tool_name":"Bash","cwd":"%s","tool_input":{"command":"%s"}}' "$W" "$1" | bash "$HOOK" 2>&1; }
reset; expect "pptx: заголовки-темы и триады" "заголовки-темы" "$(fire "$W/deck_bad.pptx")"
reset; expect "pptx: тезисные заголовки молчат" - "$(fire "$W/deck_good.pptx")"
reset; mv "$W/deck_good.pptx" "$W/deck_good.bak"; expect "Bash: собранная колода поймана" "deck_bad.pptx" "$(bash_fire "python3 build.py deck_bad.pptx")"
reset; expect "Bash: посторонняя команда молчит" - "$(bash_fire "ls -la")"

# авто-жанр: человеческая научная статья (канцелярит — норма) даёт мягкую строку, не требование править;
# повтор молчит; тот же канцелярит + чатбот-артефакт остаётся жёстким
python3 - "$W" <<'PY'
import sys
w=sys.argv[1]
sci=("Данное исследование является продолжением работы авторов. В соответствии с методикой анализ осуществлялся в рамках выборки из 120 школ. "
     "Таким образом, полученные результаты являются основанием для пересмотра программы. Следует отметить, что данный подход применялся в соответствии с протоколом. ")*5
open(w+"/sci.md","w").write(sci)
open(w+"/sci_bot.md","w").write(sci+"Надеюсь, это поможет! Отличный вопрос!")
PY
reset; expect "авто-жанр: научный текст — мягко" "genre science" "$(fire "$W/sci.md")"
expect "авто-жанр: повтор молчит" - "$(fire "$W/sci.md")"
reset; expect "авто-жанр: чатбот-артефакт остаётся жёстким" "слоп-скан" "$(fire "$W/sci_bot.md")"

# HTML: стили и скрипты не должны топить кириллицу (иначе страница с CSS молча пропускается);
# парный кейс — та же разметка с чистым текстом. HTML-колода из <section class="slide"> идёт в режим слайдов.
python3 - "$W" <<'PY'
import sys
w=sys.argv[1]
css="<style>"+".a{color:red;margin:0;padding:0;font-family:Helvetica}"*80+"</style><script>"+"function f(){return 1};"*80+"</script>"
bad=("В современном мире автоматизация играет ключевую роль. Данное решение позволяет осуществлять управление. Подход открывает новые горизонты. ")*12
clean=open(w+"/clean.md").read()
page=lambda t:"<html><head>"+css+"</head><body><p>"+t+"</p></body></html>"
open(w+"/page_bad.html","w").write(page(bad))
open(w+"/page_clean.html","w").write(page(clean*2))
deck="<html><head>"+css+"</head><body>"+"".join('<section class="slide"><h2>%s</h2><p>Наша команда работает быстро, надёжно и удобно для всех клиентов компании</p></section>'%h for h in ["Введение","Обзор","Проблема","Решение","Результаты","Выводы"])+"</body></html>"
open(w+"/deck.html","w").write(deck)
PY
reset; expect "HTML со стилями: слоп пойман" "слоп-скан page_bad.html" "$(fire "$W/page_bad.html")"
reset; expect "HTML со стилями: чистый молчит" - "$(fire "$W/page_clean.html")"
reset; expect "HTML-колода: заголовки-темы" "заголовки-темы" "$(fire "$W/deck.html")"

# блок: жёсткий маркер в собранном скриптом файле (Write/Edit закрывает PreToolUse-хук)
reset; expect "Bash: колода без жёстких маркеров — без block" "deck_bad.pptx" "$(bash_fire "python3 build.py deck_bad.pptx" | grep -v '"decision": "block"')"
python3 - "$W" <<'PY'
import sys,zipfile
with zipfile.ZipFile(sys.argv[1]+"/deck_bot.pptx","w") as z:
    for i in range(1,5): z.writestr(f"ppt/slides/slide{i}.xml",'<p:sld><a:p><a:r><a:t>Выручка выросла на 12% за год</a:t></a:r></a:p><a:p><a:r><a:t>Надеюсь, это поможет! Основной вклад дал корпоративный сегмент, розница просела на три процента</a:t></a:r></a:p></p:sld>')
PY
reset; expect "Bash: чатбот-фраза в колоде — block" '"decision": "block"' "$(bash_fire "python3 build.py deck_bot.pptx")"
# файл, найденный обходом и не названный в команде, только подсказывается: его текст мог прийти не от нас
reset; expect "Bash: неназванный файл с чатбот-фразой виден" "deck_bot.pptx" "$(bash_fire "python3 build.py")"
reset; expect "Bash: неназванный файл не блокирует" - "$(bash_fire "python3 build.py" | grep -o '"decision": "block"')"
mkdir -p "$W/sub"; cp "$W/deck_bot.pptx" "$W/sub/deck_cd.pptx"; rm -f "$W/deck_bot.pptx"
reset; expect "Bash: cd в подкаталог глубже glob — колода найдена" "deck_cd.pptx" "$(bash_fire "cd sub/ && python3 build.py deck_cd.pptx")"
mkdir -p "$W/a/b"; mv "$W/sub/deck_cd.pptx" "$W/a/b/deck_deep.pptx"
reset; expect "Bash: cd a/b — колода найдена" "deck_deep.pptx" "$(bash_fire "cd a/b && python3 build.py")"
reset; expect "Bash: без cd свежая колода на глубине 2 найдена" "deck_deep.pptx" "$(bash_fire "python3 build.py")"
mkdir -p "$W/a/b/c/d"; mv "$W/a/b/deck_deep.pptx" "$W/a/b/c/d/deck_too_deep.pptx"
reset; expect "Bash: глубже трёх уровней не ищем" - "$(bash_fire "python3 build.py" | grep -o deck_too_deep)"
mkdir -p "$W/node_modules/x"; mv "$W/a/b/c/d/deck_too_deep.pptx" "$W/node_modules/x/deck_nm.pptx"
reset; expect "Bash: node_modules пропускаем" - "$(bash_fire "python3 build.py" | grep -o deck_nm)"
rm -f "$W/node_modules/x/deck_nm.pptx"
reset; expect "Bash: marp-сборка доходит до разбора" "deck_bad.pptx" "$(touch "$W/deck_bad.pptx"; bash_fire "marp slides.md -o deck_bad.pptx")"

# PDF (через pdftotext) и тире сверх лимита в чистом тексте
if command -v pdftotext >/dev/null && python3 -c "import reportlab" 2>/dev/null; then
python3 - "$W" <<'PY'
import sys
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import ParagraphStyle
w=sys.argv[1]
pdfmetrics.registerFont(TTFont("A", "/System/Library/Fonts/Supplemental/Arial.ttf"))
st=ParagraphStyle("p", fontName="A", fontSize=11, leading=15)
bad=("В современном мире автоматизация играет ключевую роль. Данное решение позволяет осуществлять управление. Эксперты считают, что подход открывает новые горизонты. ")*8
SimpleDocTemplate(w+"/doc_bad.pdf").build([Paragraph(bad, st)])
SimpleDocTemplate(w+"/doc_clean.pdf").build([Paragraph(open(w+"/clean.md").read()*2, st)])
PY
reset; expect "PDF: слоп пойман" "слоп-скан doc_bad.pdf" "$(fire "$W/doc_bad.pdf")"
reset; expect "PDF: чистый молчит" - "$(fire "$W/doc_clean.pdf")"
else
  echo "  (PDF пропущен: нет pdftotext или reportlab)"
fi
python3 - "$W" <<'PY'
import sys
w=sys.argv[1]; c=open(w+"/clean.md").read()*2
open(w+"/dashes.md","w").write(c.replace(", потому что", " — потому что").replace(" и нашли", " — и нашли"))
PY
reset; expect "тире сверх лимита в чистом тексте" "тире:" "$(fire "$W/dashes.md")"

# расшифровка интервью: живая речь со спикерами и таймкодами — не слоп модели; тот же текст без разметки ловится (bad.md)
python3 - "$W" <<'PY2'
import sys
w=sys.argv[1]
bad=("В современном мире автоматизация играет ключевую роль. Данное решение позволяет осуществлять управление. "
     "Это не просто инструмент — это новый способ мышления. Эксперты считают, что подход открывает новые горизонты. ")*7
src=[t.strip() for t in bad.split(". ") if t.strip()]
rows=[f"[00:{i:02d}:10] {'Интервьюер' if i%2 else 'Респондент'}: {t}." for i,t in enumerate(src)]
open(w+"/interview.md","w").write("\n".join(rows))
open(w+"/plain_lines.md","w").write("\n".join(t+"." for t in src))
PY2
check silent "расшифровка интервью (спикеры, таймкоды)" "$W/interview.md"
check fires  "тот же текст построчно без разметки"      "$W/plain_lines.md"
python3 - "$W" <<'PY2'
import sys
w=sys.argv[1]
heads=["Итог","Риск","Вывод","Шаг 1","Важно","Контекст","Цель","План"]
bad="В современном мире автоматизация играет ключевую роль. Данное решение позволяет осуществлять управление. Это не просто инструмент — это новый способ мышления. Эксперты считают, что подход открывает новые горизонты."
open(w+"/labels.md","w").write("\n".join(f"{h}: {bad}" for h in heads))
PY2
check fires  "документ из строк «Итог:/Риск:» — не расшифровка" "$W/labels.md"

# два раза за ход на один файл: третий отчёт по тому же файлу молчит, другой файл того же хода говорит
export TURN_GATE_DIR="$W/gate"
printf '{"type":"user","uuid":"u1","message":{"role":"user","content":"задача"}}\n' > "$W/tr.jsonl"
cp "$W/plain_lines.md" "$W/t1.md"; cp "$W/plain_lines.md" "$W/t2.md"; cp "$W/plain_lines.md" "$W/t3.md"
fire_t() { printf '{"session_id":"s1","transcript_path":"%s","tool_name":"Write","tool_input":{"file_path":"%s"}}' "$W/tr.jsonl" "$1" | bash "$HOOK" 2>&1; }
reset; expect "лимит 2 на файл: первый отчёт" "слоп-скан" "$(fire_t "$W/t1.md")"
reset; expect "лимит 2 на файл: второй отчёт" "слоп-скан" "$(fire_t "$W/t1.md")"
reset; expect "лимит 2 на файл: третий по тому же файлу молчит" - "$(fire_t "$W/t1.md")"
reset; expect "другой файл в том же ходу говорит" "слоп-скан" "$(fire_t "$W/t2.md")"
reset; expect "третий файл в том же ходу говорит" "слоп-скан" "$(fire_t "$W/t3.md")"
printf '{"type":"user","uuid":"u2","message":{"role":"user","content":"дальше"}}\n' >> "$W/tr.jsonl"
reset
expect "раз за ход: в новом ходу снова говорит" "слоп-скан" "$(fire_t "$W/t1.md")"

# вид документа: тот же чистый текст с шапкой «заголовок + дата» и с шаблонными разделами говорит, с одним заголовком молчит
unset TURN_GATE_DIR
{ printf '# Автоматизация рутины\n\n'; cat "$W/clean.md"; } > "$W/titled.md"
{ printf '# Автоматизация рутины\n\n**Дата:** 21 ноября 2026\n\n'; cat "$W/clean.md"; } > "$W/hero.md"
{ printf '# Автоматизация рутины\n\n## Кратко\n\n'; cat "$W/clean.md"; printf '\n\n## Следующие шаги\n\nСобрать список проектов.\n'; } > "$W/sections.md"
check silent "вид: один заголовок и абзацы" "$W/titled.md"
reset; expect "вид: шапка с датой под заголовком" "вид: шапка" "$(fire "$W/hero.md")"
reset; expect "вид: шаблонные разделы" "вид: шаблонные разделы" "$(fire "$W/sections.md")"

# мусор на входе не роняет
out3=$(printf 'не json' | bash "$HOOK" 2>&1); rc=$?
[ "$rc" = 0 ] && [ -z "$out3" ] && pass=$((pass+1)) || { fail=$((fail+1)); failed+=("мусор на stdin"); echo "  ✗ мусор на stdin"; }

echo
if [ "$fail" -eq 0 ]; then printf '✅ %d/%d passed\n' "$pass" "$pass"; exit 0
else printf '❌ %d passed, %d FAILED: %s\n' "$pass" "$fail" "${failed[*]}"; exit 1; fi
