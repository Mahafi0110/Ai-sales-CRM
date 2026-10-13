"""Checks that your AI key and model work.  Usage:  python -m scripts.check_ai"""
import logging

from app.ai.errors import AIError
from app.ai.llm import get_llm, model_name
from app.ai.runner import translate_error
from app.core.config import get_settings


def main() -> None:
    logging.disable(logging.CRITICAL)  # keep the output short: we print our own message
    settings = get_settings()
    print(f"Provider: {settings.llm_provider}   Model: {model_name()}")
    try:
        llm = get_llm()
    except AIError as exc:
        raise SystemExit(f"Not ready: {exc.detail}")
    try:
        answer = llm.invoke("Reply with the single word: ready")
    except Exception as exc:
        raise SystemExit(f"The AI call failed: {translate_error(exc).detail}\n(Technical detail: {str(exc)[:300]})")
    print("AI answered:", str(answer.content).strip()[:80])
    print("All good. You can use the AI buttons in the app.")


if __name__ == "__main__":
    main()
