# Сборщик ТЗ

Облачный агент Cursor на Grok 4.7. Заказчик переписывается с Telegram-ботом. Агент ведёт его по девяти этапам, пока не сложится картина проекта, предлагает заметные улучшения и оставляет решение за заказчиком. Файлы из чата сохраняются и входят в разбор.

После каждого закрытого этапа подробный результат пишется в облачное хранилище деплоя и в артефакты агента, а также ставится в очередь на письмо. Пока SMTP не настроен, текст отчёта не пропадает: его забирает почасовая отправка, как только появятся секреты почты.

Адрес по умолчанию: `viktor26ru@gmail.com`. Его перекрывает секрет `TZ_OWNER_EMAIL`.

## Что помнит агент

Состояние живёт не в памяти процесса.

- Ключи `brief:<чат>` и журнал файлов `brief.json`, `progress.txt`, `turns/`, `files/`, `reports/` — по каждому чату.
- Артефакт `brief` обновляется по ходу диалога, `stage-report` — на закрытии этапа, `registry` — список всех диалогов.
- Повтор того же апдейта Telegram не задваивает реплику. Повтор того же отчёта не шлёт второе письмо.

В каждом ответе бота есть плашка: номер этапа из 9, что уже закрыто, чего не хватает и что ещё впереди. Команды `/progress` и `/report` отвечают без модели. `/help` объясняет правила.

Общий журнал памяти BDK выключен: реплики одного заказчика не должны всплывать в другом чате.

## Секреты

В репозитории только имена. Токен бота из переписки лучше перевыпустить в BotFather и задать новый.

```text
bdk secrets set tz-agent TELEGRAM_BOT_TOKEN
bdk secrets set tz-agent TELEGRAM_WEBHOOK_SECRET
bdk secrets set tz-agent SMTP_USER
bdk secrets set tz-agent SMTP_PASSWORD
bdk secrets set tz-agent TZ_OWNER_EMAIL
```

`SMTP_USER` и `SMTP_PASSWORD` — ящик Gmail и пароль приложения. Отправка идёт на `smtp.gmail.com:465`. Без них отчёты остаются в очереди и в файлах `reports/`.

После секретов нужен повторный деплой. Webhook:

```text
WEBHOOK_URL="<стабильный URL деплоя>/v1/channels/telegram/webhook" \
TELEGRAM_BOT_TOKEN="..." \
TELEGRAM_WEBHOOK_SECRET="..." \
node scripts/set-telegram-webhook.mjs
```

Telegram присылает секрет в заголовке `X-Telegram-Bot-Api-Secret-Token`. Локальный `bdk serve` с той же машины принимает webhook без этого заголовка.

## Проверки

```text
npm test
npm run check
npx bdk validate
npx bdk call read_brief --input '{"chatId":"1001"}'
```

Модельный прогон: `npx bdk eval --list`, затем `npx bdk eval interview/record-problem`, когда есть ключ Cursor.
