# Ограничитель частоты для хуков, которые пишут additionalContext после вызовов
# инструментов. Подключается строкой:
#   source "$(dirname "${BASH_SOURCE[0]}")/lib/turn_gate.sh"
# и вызывается прямо перед выводом напоминания:
#   turn_gate <имя> <раз_за_ход> <потолок_за_сессию|0> "$input" || exit 0
#
# Зачем: Sonnet 5.5 и Haiku 5.5 принимают служебный текст после каждого tool
# result за prompt injection и могут пропустить настоящие сообщения пользователя
# Поэтому напоминание звучит не чаще N раз за ход.
#
# Ход начинается с последней реплики пользователя в транскрипте: запись
# type=user, не isMeta, без tool_result. Харнесс номер хода хуку не передаёт.
# У субагента свой контекст, поэтому ключ включает agent_id.
# Нет session_id или транскрипта: ход не определить, хук говорит как раньше.
# Параллельные вызовы инструментов запускают хуки одновременно, отсюда flock.

turn_gate() {
  local name="$1" per_turn="$2" cap="$3" input="$4"
  printf '%s' "$input" | TURN_GATE_DIR="${TURN_GATE_DIR:-${TMPDIR:-/tmp}/cc-turn-gate}" \
    python3 -c '
import fcntl, json, os, sys

name, per_turn, cap = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
try:
    inp = json.load(sys.stdin)
except ValueError:
    sys.exit(0)
session = inp.get("session_id") or ""
tpath = inp.get("transcript_path") or ""
agent = inp.get("agent_id") or ""
if not session or not os.path.isfile(tpath):
    sys.exit(0)

def turn_key():
    with open(tpath, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - 8_000_000))
        lines = f.read().splitlines()
    for raw in reversed(lines):
        if b"\"user\"" not in raw:
            continue
        try:
            d = json.loads(raw)
        except ValueError:
            continue
        if d.get("type") != "user" or d.get("isMeta"):
            continue
        c = (d.get("message") or {}).get("content")
        if isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
            continue
        return d.get("uuid") or "nouuid"
    return "unknown"

d = os.path.join(os.environ["TURN_GATE_DIR"], session, agent or "main")
os.makedirs(d, exist_ok=True)
path = os.path.join(d, name + ".json")
with open(path, "a+") as f:
    fcntl.flock(f, fcntl.LOCK_EX)
    f.seek(0)
    try:
        st = json.loads(f.read() or "{}")
    except ValueError:
        st = {}
    key = turn_key()
    n = st.get("n", 0) if st.get("turn") == key else 0
    total = st.get("total", 0)
    if n >= per_turn or (cap and total >= cap):
        sys.exit(3)
    f.seek(0)
    f.truncate()
    json.dump({"turn": key, "n": n + 1, "total": total + 1}, f)
' "$name" "$per_turn" "$cap" 2>/dev/null
  local rc=$?
  # 3 — лимит исчерпан; любой другой код (в том числе падение python) — говорим, как до ограничителя.
  [ "$rc" -eq 3 ] && return 1
  return 0
}
