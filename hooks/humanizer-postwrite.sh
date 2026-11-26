#!/bin/bash
# PostToolUse (Edit|Write и Bash): после записи русскоязычного документа (.md/.txt/.html/.rst/.docx/.pptx)
# гонит slop_scan.py из скилла humanizer-ru и, если текст слоповый, подсказывает
# править по скиллу. Правила чистого письма скилл даёт до работы, этот хук меряет результат после.
#
# Молчит на: коде, коротком (<150 слов) без жёстких маркеров, служебных путях
# (~/.claude, skills, memory, handoffs, CLAUDE.md, CHANGELOG, LICENSE), чистом тексте
# (счёт ≥80, без кластеров и чатбот-артефактов) и повторе без изменений. После правки сам отдаёт «было/стало» и пропавшие факты.
# Фразу чат-бота, «не просто X, а Y» и безымянную атрибуцию показывает при любой длине.
# В английском тексте показывает только фразы чат-бота и «not X but Y»; слова-штампы там молчат.
# Никогда не роняет вызывающего: любая ошибка — тихий выход.
#
# Регрессия: bash hooks/tests/test-humanizer-postwrite.sh
# Кириллица: весь разбор в lib/humanizer_postwrite.py на python3 (tr/sed/grep на многобайтовых символах ненадёжны).

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/lib/turn_gate.sh"

input=$(cat)

# Предфильтр до старта python (~100 мс на каждом Bash/Edit): нет расширения
# документа во вводе — документа нет. Bash ещё пропускаем на командах сборки
# (скрипт может писать колоду без расширения в команде: «cd a/b && python3 build.py»).
# Шаблоны ASCII, кириллица не участвует.
shopt -s nocasematch
if ! [[ "$input" =~ \.(md|txt|html?|rst|docx|pptx|pdf)([^a-z0-9]|$) ]]; then
  # тот же список, что BUILD_RE в lib/humanizer_postwrite.py
  [[ "$input" =~ \"tool_name\":\ ?\"Bash\" && "$input" =~ (python|node|npx|claro|pandoc|soffice|libreoffice|marp|typst|weasyprint|make) ]] || exit 0
fi
shopt -u nocasematch
out=$(printf '%s' "$input" | HUMANIZER_SCAN="${HUMANIZER_SCAN:-$HERE/../scripts}" \
  STAMPS="${HUMANIZER_STAMPS:-$HOME/.claude/logs/humanizer-postwrite.stamps}" python3 "$HERE/lib/humanizer_postwrite.py" 2>/dev/null)

# Блок (жёсткие маркеры в собранном файле) проходит всегда. Отчёт не чаще двух
# раз за ход на один файл или одну команду сборки: слоп-скан и «было/стало» после правки.
# Общий лимит на хук глушил третий файл хода (md, docx, pptx подряд), 21.11.2026.
if [ -n "$out" ] && [[ "$out" != *'"decision"'* ]]; then
  key=$(printf '%s' "$input" | python3 -c 'import json,sys,hashlib; t=json.load(sys.stdin).get("tool_input") or {}; print(hashlib.sha1((t.get("file_path") or t.get("command") or "").encode()).hexdigest()[:10])' 2>/dev/null)
  turn_gate "humanizer-postwrite-$key" 2 0 "$input" || exit 0
fi
if [ -n "$out" ]; then
  printf '%s\n' "$out"
fi
exit 0
