# VPd06 — консольный ассистент через ProxyAPI

Небольшой чат в терминале с сохранением истории диалога и переключением между двумя режимами:

1. **Думающая модель** (по умолчанию) — Claude Sonnet 4.5+ через Anthropic Messages API с `thinking` и выводом показателей reasoning.
2. **Обычная модель** — OpenAI-совместимый Chat Completions.

Запросы идут через [ProxyAPI](https://proxyapi.ru/docs).

## Быстрый старт

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Скопируйте `.env.example` в `.env` и укажите ключ ProxyAPI:

```env
OPENAI_API_KEY=sk-your-proxyapi-key-here

OPENAI_BASE_URL=https://api.proxyapi.ru/openai/v1
OPENAI_MODEL=gpt-4o-mini

ANTHROPIC_BASE_URL=https://api.proxyapi.ru
CLAUDE_MODEL=anthropic/claude-sonnet-4-5
THINKING_BUDGET=10000
MAX_TOKENS=16000
```

Запуск:

```powershell
.\.venv\Scripts\Activate.ps1
python chat_test.py
```

Без активации venv:

```powershell
.\.venv\Scripts\python.exe chat_test.py
```

## Как пользоваться

1. При старте выберите режим:
   - `1` — думающая модель Claude (**по умолчанию**, если просто нажать Enter)
   - `2` — обычная модель через Chat Completions
2. Пишите сообщения в консоль — ассистент отвечает с учётом истории.
3. Выход: `exit`, `quit` или `выход`.

В думающем режиме перед ответом печатается блок **Reasoning**: модель, токены и ход рассуждений (если API его вернул).

## Что внутри

| Файл | Назначение |
| --- | --- |
| `chat_test.py` | Основной скрипт: диалог, режимы, история |
| `requirements.txt` | Зависимости: `openai`, `anthropic`, `python-dotenv` |
| `.env` | Ключ и адреса API (не коммитить) |
| `.env.example` | Шаблон переменных окружения |
| `dialog_history.json` | Сохранённая история диалога (создаётся при работе) |

### Функции

- `chat_openai()` — обычная модель через Chat Completions
- `chat_claude_thinking()` — Claude с `thinking` и метриками reasoning
- `save_history()` / `load_history()` — сохранение и подгрузка истории между запросами
- `reset_dialog()` — сброс истории
- `choose_mode()` — выбор режима в начале работы
- `run_dialog()` — интерактивный цикл чата

## Подключение к ProxyAPI

- **OpenAI SDK**: `base_url=https://api.proxyapi.ru/openai/v1` (или единый `https://api.proxyapi.ru/v1`)
- **Anthropic SDK**: `base_url=https://api.proxyapi.ru` — SDK сам дописывает `/v1/messages`

Один и тот же ключ ProxyAPI используется для обоих клиентов.

Документация: https://proxyapi.ru/docs  
Anthropic Messages: https://proxyapi.ru/docs/messages  
Reasoning: https://proxyapi.ru/docs/reasoning
