#!/bin/bash
# PreToolUse: текст, который уходит наружу (письмо и черновик, артефакт, Claude Docs, тело PR,
# issue и релиза через gh, длинный набор текста в браузере), до отправки проходит slop_scan.py
# из скилла humanizer-ru. При жёстком признаке (чатбот-фраза, антитеза, безымянная атрибуция,
# паттерны раздела 15 и 14 с нулём у людей, подводка-анонс, любое тире в русском тексте, значки
# вместо слов) вызов отклоняется с причиной. Шапка под заголовком и шаблонные разделы отклоняются
# везде, кроме текста PR, issue и релиза. Английский текст проверяется по slop_scan.py --lang en.
# Тот же текст второй раз за час проходит: цитату или продиктованное пользователем не править. Каждый
# такой пропуск пишется в passed.log рядом со штампами.
# Никогда не роняет вызывающего: любая ошибка — тихий выход.
#
# Регрессия: bash hooks/tests/test-humanizer-outbound.sh

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

input=$(cat)

# Bash: проверяем только gh, который пишет в чужие или свои PR, issue и релизы. Шаблон ASCII.
if [[ "$input" =~ \"tool_name\":\ ?\"Bash\" ]] && ! [[ "$input" =~ gh\ +(pr|issue|release|api) ]]; then
  exit 0
fi

out=$(printf '%s' "$input" | HUMANIZER_SCAN="${HUMANIZER_SCAN:-$HERE/../scripts}" \
  STAMPS="${HUMANIZER_OUTBOUND_STAMPS:-$HOME/.claude/logs/humanizer-outbound.d}" python3 "$HERE/lib/humanizer_outbound.py" 2>/dev/null)

if [ -n "$out" ]; then
  printf '%s\n' "$out"
fi
exit 0
