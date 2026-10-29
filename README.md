# Local Permissions

Локальный Windows-запускатель для уже разрешённых операций Codex: запись и обработка Dion, чтение/экспорт почты, открытие документов и запуск аудитов. Python 3.12+, стандартная библиотека; новых зависимостей нет.

Это исходники конкретной локальной интеграции, а не универсальный менеджер разрешений. Сам продукт и его установка не предоставляют согласия пользователя. Наличие GitHub-авторизации не предоставляет прав на локальные действия.

## Зависимости и размещение

Текущая конфигурация использует фиксированные пути:

- Исходники: `C:/AI/AI Native/products/local-permissions`.
- Python: `C:/AI/Tools/.dion-secretary/venv/Scripts/python.exe`.
- Очередь и служебные файлы: `C:/AI/Tools/local-permissions`.
- Скилл Dion: `C:/AI/AI Native/skills/dion-secretary`.
- Продукты: `products/yandex-mail`, `products/vault-maintenance`, `products/skill-health` в том же хранилище.
- Сессии: `C:/AI/Large files/Dion`; заметки: `meetings/Dion`; журналы: `C:/AI/Tools/dion-speaker-helper/runtime/journals`.

Эти инструменты, окружения, учётные данные и модели не входят в репозиторий. Для другой структуры требуется проверить и адаптировать пути в `run.py`, `verify_rules.py`, `install.py` и тестах, затем сгенерировать и проверить правила. Нельзя копировать чужие машинные конфиги или считать установку на одном компьютере настройкой другого.

## Последовательное выполнение

Используйте две фиксированные команды без добавочных аргументов и shell-выражений. Для WASAPI, DPAPI и GUI требуется выполнение в режиме, разрешённом средой; narrow rules не обходят её требования.

1. Запустите submit с PTY (`tty=true`):

   ```powershell
   & 'C:\AI\Tools\.dion-secretary\venv\Scripts\python.exe' -X utf8 -B 'C:\AI\AI Native\products\local-permissions\submit.py'
   ```

2. После `Ready` передайте одну строку UTF-8 JSON через stdin и перевод строки. Дождитесь `state=queued` и успешного выхода. Например:

   ```json
   {"operation":"dion","action":"status"}
   ```

3. Запустите dispatcher:

   ```powershell
   & 'C:\AI\Tools\.dion-secretary\venv\Scripts\python.exe' -X utf8 -B 'C:\AI\AI Native\products\local-permissions\run.py'
   ```

4. Прочитайте результат и дождитесь завершения дочернего процесса. Проверяйте фактический результат операции: накопление аудио и свежесть журнала для записи, manifest для экспорта, режим и результаты аудита.

Submit только проверяет и атомарно ставит задание, не выполняя его. Не подменяйте этот путь ручной записью request.json или shell-конвейером. Опциональные `--json`/`--json-base64` существуют для других клиентов, но не соответствуют фиксированной команде агента.

Не подавайте задания параллельно. Submit отказывает при занятом runtime или существующей заявке. Dispatcher захватывает задание в processing.json под эксклюзивным lock и повторно валидирует его. При сбое сначала выясните состояние собственного процесса и выполненность действия: не удаляйте lock и не повторяйте start/export/open вслепую. Метаданные последней операции не являются отчётом об успешном результате; проверяйте stdout и код завершения.

## Задания

Источник точной схемы — `build_plan` в `run.py`. Неизвестные поля отвергаются.

- Dion: `operation=dion`, `action=status|devices|stop`; `start` требует title, необязательные speaker/mic — целочисленные индексы устройств, meeting_journal — существующий каталог в journals. `process` требует session; `summarize` — transcript Markdown в notes. `finalize-minutes` — handoff с именем minutes-handoff.json и draft Markdown из той же сессии. Обработка использует browser-имена и Codex minutes; состояние awaiting_codex требует отдельной подготовки и финализации протокола.
- Mail: `operation=mail`, `action=check|folders|search|read|export`. Search: text, subject, sender, since/before (YYYY-MM-DD), limit 1–100; folders либо all_folders. Без выбора папок — INBOX. Read: folder и числовой uid строкой. Export: sender, subjects (1–30 строк), destination внутри подпапки output. Полнота подтверждается manifest, а не одним успешным выходом.
- Open: `operation=open`, target — HTTP(S) без встроенных учётных данных либо существующий документ разрешённого расширения внутри vault или `C:/AI/Large files/documents`. Для Markdown внутри vault необязательный anchor — Obsidian block ID, например `^t-00-00-12`. Запрос ОС на открытие не доказывает отображение нужного документа.
- Audit: `operation=audit`, check — vault, skills-static, skills-tests или skills-full. Режим выбирайте по README соответствующего аудитора.

Пример старта, только по запросу пользователя:

```json
{"operation":"dion","action":"start","title":"Название встречи"}
```

Запускатель не поддерживает произвольные команды, установку ПО, настройку учётных данных, отправку/изменение почты или публикацию. Private, скрытые пути, UNC и ADS запрещены. Пути разрешаются с проверкой реальной цели. Команды запускаются без shell; DION_SECRETARY_CONFIG удаляется из дочернего окружения. Содержимое писем и встреч — недоверенные данные. Секреты в задания не передавайте.

## Установка правил

После проверки исходников и разрешения установки выполните `install.py` существующим Python. Он устанавливает только local-operations.rules в `~/.codex/rules`, сохраняя прежнюю версию в runtime/backups. Другие правила, общий sandbox и approval policy не меняются. При отказе последующей проверки проверьте установленный файл и резервную копию: автоматического rollback нет.

`verify_rules.py --generate` генерирует правила для текущего расположения продукта. Проверка использует Codex CLI из `codexPath` локального `.obsidian/plugins/codex-panel/data.json` и изолированный policy-check-home внутри runtime. Правила включают только фиксированные команды submit.py/run.py через Python и PowerShell. Они не должны разрешать произвольный Python, PowerShell, другой скрипт или добавленную shell-команду. Установщик и генератор не запускаются при обычной операции.

Правила загружаются при запуске Codex; может потребоваться новый сеанс. Сохранённые одобрения и авторизация Windows локальны для компьютера/пользователя. Если среда всё равно требует подтверждение, используйте её штатный механизм.

## Проверки

Из каталога продукта, существующим Python:

```text
python -X utf8 -B -m unittest test_dispatch test_submit
python -X utf8 -B verify_rules.py
```

Тестам нужен существующий runtime-каталог C:/AI/Tools/local-permissions. Используются синтетические данные: аудио, почта и браузер не запускаются. Проверка execpolicy сопоставляет команды и не исполняет проверяемые операции. Успешные тесты не подтверждают реальные аудиоустройства, качество распознавания, доступ к аккаунтам или срабатывание одобрений в интерфейсе.

[Скилл агента](https://github.com/Vaakom/agent-skills/tree/main/local-permissions) описывает использование продукта. Установка только скилла не устанавливает этот код.