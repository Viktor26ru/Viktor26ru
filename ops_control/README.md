# Независимый контур мониторинга ЦОВ

Работает в Cursor Cloud отдельно от прод-хостов Пятёрочки, Чижика и ПМ.

```bash
python3 ops_control/app.py          # передний план
python3 ops_control/app.py --daemon # фон + /api/health
make ops-test
make ops-run
```

Дашборд: `http://127.0.0.1:8787/?key=...` (ключ в `ops_control/.secrets.env`).  
Telegram: бот `@Crazynewaibot`, привязка `/start <BIND_CODE>`.  
MAX: команды и ответы идут через SSH на каждый прод-бот, токены с хостов не копируются в git.  
Прод сам не рестартуется: при сбое приходит предложение в Telegram и MAX, рестарт только командой `/restart …`.

Секреты и ключи SSH не коммитятся. Пример: `ops_control/secrets.example.env`.
План системы: `ops_control/PLAN.md`.
