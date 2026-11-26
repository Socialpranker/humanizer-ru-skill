#!/bin/bash
# Регрессия для hooks/humanizer-outbound.sh (PreToolUse, проверка текста перед отправкой наружу).
# Каждый «молчит» имеет парный «отклоняет» с одним отличием: иначе тишина может значить поломку.
# Мутация: HUMANIZER_SCAN=/пустая/папка bash test-...sh — тест обязан покраснеть.
#
# Запуск:  bash hooks/tests/test-humanizer-outbound.sh

HOOK="${HOOK:-$(cd "$(dirname "$0")/.." && pwd)/humanizer-outbound.sh}"
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
export HOOKLOG_FILE="$W/hooks.log"
export HUMANIZER_OUTBOUND_STAMPS="$W/stamps"
pass=0; fail=0; failed=()

# Генерирует JSON вызова: py <tool> <python-выражение tool_input>, переменные текста ниже.
mk() {
  python3 - "$W" "$1" "$2" <<'PY'
import json, sys
w, tool, expr = sys.argv[1:4]
CLEAN = ("Мы перенесли встречу на четверг, потому что подрядчик не успевает подготовить смету. "
         "Смету он пришлёт в среду вечером, и я сразу перешлю её вам.")
DASHES = ("Встреча — в четверг, смета — в среду, оплата — после подписания. "
          "Подрядчик просил не торопить его со сроками.")
ONEDASH = CLEAN + " Итоговая сумма — около двухсот тысяч, точнее скажу после сметы."
CHAT = "Надеюсь, это поможет! Смета будет в среду вечером."
ANTI = "Смета нужна не только для бухгалтерии, но и для банка, который выдаёт кредит."
DOC = "<p>Таблица ниже сравнивает три сметы подрядчиков по цене и срокам работ.</p>"
DOCOK = "<p>Дешевле всех смета Петрова: двести тысяч за три недели работы.</p>"
EN_BAD = "Great question! It's not just a cache, it's a strategy. Let's dive in and see how it works."
EN_OK = "The cache keeps responses for ten minutes, so repeated requests skip the database entirely."
LONG_BAD = ("Не поймите меня неправильно, документация нужна. " + CLEAN + " ") * 2
HERO = "# Перенос встречи\n\n*Краткая справка*\n\n**Дата:** 21 ноября 2026\n\n" + CLEAN
TITLED = "# Перенос встречи\n\n" + CLEAN
SECTIONS = "## Кратко\n\n" + CLEAN + "\n\n## Контекст\n\n" + CLEAN + "\n\n## Итог\n\n" + CLEAN
LEADIN = "Встречу переносим на четверг. Причин две. Подрядчик не успевает подготовить смету, а банк ждёт её до пятницы."
f = open(w + "/body.md", "w"); f.write(EN_BAD); f.close()
f = open(w + "/hero.md", "w"); f.write(HERO + "\n\n" + SECTIONS); f.close()
# eval только над выражениями, записанными в этом же тесте: так входы собираются из констант выше
print(json.dumps({"tool_name": tool, "tool_input": eval(expr)}, ensure_ascii=False))
PY
}
run() { mk "$2" "$3" | bash "$HOOK" 2>&1; }
check() {  # check <deny|silent> <имя> <tool> <tool_input-выражение>
  local out ok; rm -rf "$HUMANIZER_OUTBOUND_STAMPS"
  out=$(run "$1" "$3" "$4")
  case "$1" in
    deny)   echo "$out" | grep -q '"permissionDecision": "deny"' && ok=1 || ok=0 ;;
    silent) [ -z "$out" ] && ok=1 || ok=0 ;;
  esac
  if [ "$ok" = 1 ]; then pass=$((pass+1)); else fail=$((fail+1)); failed+=("$2"); printf '  ✗ %s\n' "$2"; fi
}

G=mcp__d192aa97-3dd3-487d-a752-99c4a50d214c__send_message
check deny   "письмо: три тире"                 "$G" '{"to":"a@b.c","body":DASHES}'
check silent "письмо: чистое"                   "$G" '{"to":"a@b.c","body":CLEAN}'
check deny   "письмо: одно тире на 40 слов"     "$G" '{"to":"a@b.c","body":ONEDASH}'
check deny   "письмо: чатбот-фраза"             "$G" '{"to":"a@b.c","body":CHAT}'
check deny   "письмо: не только X, но и Y"      "$G" '{"to":"a@b.c","body":ANTI}'
check deny   "черновик: три тире"               mcp__x__create_draft '{"body":DASHES}'
check deny   "артефакт: текст о документе"      mcp__claude-artifacts__publish_version '{"content":"<html><body>"+DOC+"</body></html>"}'
check silent "артефакт: чистый"                 mcp__claude-artifacts__publish_version '{"content":"<html><body>"+DOCOK+"</body></html>"}'
check deny   "правка артефакта: new_text"       mcp__claude-artifacts__edit_version '{"edits":[{"old_text":"x","new_text":DOC}]}'
check deny   "gh pr create: heredoc EN"         Bash '{"command":"gh pr create --title T --body \"$(cat <<'"'"'EOF'"'"'\n"+EN_BAD+"\nEOF\n)\""}'
check silent "gh pr create: чистый EN"          Bash '{"command":"gh pr create --title T --body \""+EN_OK+"\""}'
check deny   "gh pr comment: --body EN"         Bash '{"command":"gh pr comment 5 --body \""+EN_BAD+"\""}'
check deny   "gh issue create: --body-file"     Bash '{"command":"gh issue create --title T --body-file "+w+"/body.md"}'
check silent "Bash без gh: тире не важны"       Bash '{"command":"echo \""+DASHES+"\""}'
check silent "браузер: короткий ввод"           mcp__claude-in-chrome__computer '{"action":"type","text":CHAT}'
check deny   "браузер: длинный ввод"            mcp__claude-in-chrome__computer '{"action":"type","text":LONG_BAD}'
check silent "браузер: клик, не ввод"           mcp__claude-in-chrome__computer '{"action":"left_click","text":LONG_BAD}'

# Вид документа: в письме и документе отклоняется, в тексте PR и issue заголовки приняты
check deny   "письмо: шапка под заголовком"     "$G" '{"to":"a@b.c","body":HERO}'
check silent "письмо: заголовок и абзац"        "$G" '{"to":"a@b.c","body":TITLED}'
check deny   "письмо: шаблонные разделы"        "$G" '{"to":"a@b.c","body":SECTIONS}'
check deny   "документ: шапка в markdown"       mcp__x__update '{"payload":{"markdown":HERO}}'
check silent "gh issue create: шапка и разделы" Bash '{"command":"gh issue create --title T --body-file "+w+"/hero.md"}'
check deny   "письмо: подводка-анонс"           "$G" '{"to":"a@b.c","body":LEADIN}'

# Повтор того же текста проходит: цитата или продиктованное пользователем. Пропуск остаётся в журнале
rm -rf "$HUMANIZER_OUTBOUND_STAMPS"
first=$(run x "$G" '{"body":DASHES}'); second=$(run x "$G" '{"body":DASHES}')
if echo "$first" | grep -q deny && [ -z "$second" ]; then pass=$((pass+1)); else fail=$((fail+1)); failed+=("повтор проходит"); echo "  ✗ повтор проходит"; fi
if grep -q "send_message.*тире" "$HUMANIZER_OUTBOUND_STAMPS/passed.log" 2>/dev/null; then pass=$((pass+1)); else fail=$((fail+1)); failed+=("пропуск в журнале"); echo "  ✗ пропуск в журнале"; fi

echo "humanizer-outbound: $pass ok, $fail fail"
[ "$fail" = 0 ]
