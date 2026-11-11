"""
Консольный ассистент через ProxyAPI.
Два режима:
  - думающая модель: Claude (Anthropic Messages + thinking)
  - обычная модель: OpenAI-совместимый Chat Completions
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("PROXY_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.proxyapi.ru/openai/v1")
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "https://api.proxyapi.ru")

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
# Claude 4.5 Sonnet или выше (через ProxyAPI)
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "anthropic/claude-sonnet-4-5")
THINKING_BUDGET = int(os.getenv("THINKING_BUDGET", "10000"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "16000"))

HISTORY_FILE = Path(__file__).with_name("dialog_history.json")
DEFAULT_SYSTEM = "Ты полезный ассистент. Отвечай кратко и по делу."

MODE_THINKING = "thinking"
MODE_NORMAL = "normal"

openai_client = OpenAI(api_key=API_KEY, base_url=OPENAI_BASE_URL)
anthropic_client = Anthropic(api_key=API_KEY, base_url=ANTHROPIC_BASE_URL)

# История диалога: system отдельно, далее user/assistant.
system_prompt = DEFAULT_SYSTEM
messages: list[dict] = []


def reset_dialog(new_system: str | None = None) -> None:
    """Сбрасывает историю диалога."""
    global system_prompt, messages
    system_prompt = new_system or DEFAULT_SYSTEM
    messages = []
    save_history()


def save_history() -> None:
    """Сохраняет историю диалога на диск."""
    payload = {"system": system_prompt, "messages": messages}
    HISTORY_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_history() -> None:
    """Подгружает историю диалога с диска, если файл есть."""
    global system_prompt, messages
    if not HISTORY_FILE.exists():
        return
    try:
        payload = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        system_prompt = payload.get("system", DEFAULT_SYSTEM)
        messages = payload.get("messages", [])
    except (json.JSONDecodeError, OSError):
        system_prompt = DEFAULT_SYSTEM
        messages = []


def _assistant_text_from_content(content) -> str:
    """Достаёт текст ответа из content (строка или блоки Anthropic)."""
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        block_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
        if block_type == "text":
            text = block.get("text") if isinstance(block, dict) else getattr(block, "text", "")
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


def _openai_messages() -> list[dict]:
    """История в формате Chat Completions (только текстовый content)."""
    result = [{"role": "system", "content": system_prompt}]
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if role == "assistant" and not isinstance(content, str):
            content = _assistant_text_from_content(content)
        result.append({"role": role, "content": content})
    return result


def _anthropic_messages() -> list[dict]:
    """История в формате Anthropic Messages (без system)."""
    return [{"role": msg["role"], "content": msg["content"]} for msg in messages]


def chat_openai(user_message: str, model: str = OPENAI_MODEL) -> str:
    """Обычная модель через OpenAI-совместимый Chat Completions."""
    messages.append({"role": "user", "content": user_message})

    response = openai_client.chat.completions.create(
        model=model,
        messages=_openai_messages(),
    )

    assistant_reply = response.choices[0].message.content or ""
    messages.append({"role": "assistant", "content": assistant_reply})
    save_history()
    return assistant_reply


def chat_claude_thinking(
    user_message: str,
    model: str = CLAUDE_MODEL,
    thinking_budget: int = THINKING_BUDGET,
) -> tuple[str, dict]:
    """
    Думающая модель Claude через Anthropic Messages API.
    Возвращает (текст ответа, показатели reasoning).
    """
    messages.append({"role": "user", "content": user_message})

    # max_tokens должен быть больше budget_tokens
    max_tokens = max(MAX_TOKENS, thinking_budget + 1024)

    response = anthropic_client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        thinking={
            "type": "enabled",
            "budget_tokens": thinking_budget,
        },
        messages=_anthropic_messages(),
    )

    thinking_parts: list[str] = []
    text_parts: list[str] = []
    serialized_content: list[dict] = []

    for block in response.content:
        if block.type == "thinking":
            thinking_text = getattr(block, "thinking", "") or ""
            thinking_parts.append(thinking_text)
            item = {"type": "thinking", "thinking": thinking_text}
            signature = getattr(block, "signature", None)
            if signature:
                item["signature"] = signature
            serialized_content.append(item)
        elif block.type == "redacted_thinking":
            serialized_content.append(
                {
                    "type": "redacted_thinking",
                    "data": getattr(block, "data", ""),
                }
            )
        elif block.type == "text":
            text_parts.append(block.text or "")
            serialized_content.append({"type": "text", "text": block.text or ""})

    assistant_reply = "\n".join(text_parts).strip()
    # Для многоходового диалога с thinking нужно сохранять блоки thinking/signature.
    messages.append({"role": "assistant", "content": serialized_content})
    save_history()

    usage = response.usage
    metrics = {
        "model": model,
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
        "thinking_tokens": None,
        "thinking_chars": sum(len(part) for part in thinking_parts),
        "thinking_preview": "\n".join(thinking_parts).strip(),
    }

    # У части ответов Anthropic/ProxyAPI thinking-токены лежат в usage отдельно.
    for attr in ("thinking_tokens", "reasoning_tokens"):
        value = getattr(usage, attr, None)
        if value is not None:
            metrics["thinking_tokens"] = value
            break

    details = getattr(usage, "completion_tokens_details", None)
    if details is not None and metrics["thinking_tokens"] is None:
        metrics["thinking_tokens"] = getattr(details, "reasoning_tokens", None)

    return assistant_reply, metrics


def print_reasoning_metrics(metrics: dict) -> None:
    """Печатает показатели reasoning думающей модели."""
    print("\n--- Reasoning ---")
    print(f"Модель: {metrics.get('model')}")
    print(f"input_tokens: {metrics.get('input_tokens')}")
    print(f"output_tokens: {metrics.get('output_tokens')}")
    print(f"thinking_tokens: {metrics.get('thinking_tokens')}")
    print(f"thinking_chars: {metrics.get('thinking_chars')}")

    preview = metrics.get("thinking_preview") or ""
    if preview:
        short = preview if len(preview) <= 1200 else preview[:1200] + "\n… [обрезано]"
        print("Ход рассуждений:")
        print(short)
    else:
        print("Ход рассуждений: (не возвращён API / скрыт)")
    print("--- /Reasoning ---\n")


def choose_mode() -> str:
    """Выбор режима в начале работы. По умолчанию — думающая модель."""
    print("Режимы:")
    print("  1 — думающая модель (Claude + thinking) [по умолчанию]")
    print("  2 — обычная модель (OpenAI Chat Completions)")
    choice = input("Выберите режим [1/2]: ").strip()
    if choice == "2":
        return MODE_NORMAL
    return MODE_THINKING


def run_dialog() -> None:
    """Интерактивный чат. Выход: exit / quit / выход."""
    load_history()
    mode = choose_mode()

    if mode == MODE_THINKING:
        print(
            f"\nРежим: думающая модель ({CLAUDE_MODEL}). "
            "Для выхода: exit / quit / выход\n"
        )
    else:
        print(
            f"\nРежим: обычная модель ({OPENAI_MODEL}). "
            "Для выхода: exit / quit / выход\n"
        )

    if messages:
        print(f"Подгружена история: {len(messages)} сообщений.\n")

    while True:
        user_input = input("Вы: ").strip()
        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit", "выход"}:
            save_history()
            print("Диалог завершён. История сохранена.")
            break

        try:
            if mode == MODE_THINKING:
                reply, metrics = chat_claude_thinking(user_input)
                print_reasoning_metrics(metrics)
                print(f"Бот: {reply}\n")
            else:
                reply = chat_openai(user_input)
                print(f"Бот: {reply}\n")
        except Exception as exc:
            # Откатываем последнее user-сообщение, если запрос упал.
            if messages and messages[-1].get("role") == "user":
                messages.pop()
            print(f"Ошибка: {exc}\n")


if __name__ == "__main__":
    run_dialog()
