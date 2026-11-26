# scripts

- `slop_scan.py` — сканер слопа (stdlib). Использование — в шапке файла и в `../SKILL.md`.
- `tests/test_slop_scan.py` — регрессия сканера и синхронности каталога с кодом.

Запуск тестов (без записи `__pycache__`):

```bash
python3 -B -m unittest discover -s ~/.claude/skills/humanizer-ru/scripts/tests
```

Добавляя маркер в `slop_scan.py`, допиши его метку в `../references/patterns.md`, раздел «Метки сканера», иначе `test_every_marker_label_documented` красный.
