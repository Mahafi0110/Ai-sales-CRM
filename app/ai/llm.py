"""Creates the chat model the rest of the app talks to. Change provider or model in .env, nothing else."""
from app.ai.errors import AIError, AINotConfigured
from app.core.config import get_settings


def _api_key() -> str:
    s = get_settings()
    return {"gemini": s.google_api_key, "anthropic": s.anthropic_api_key, "openai": s.openai_api_key}.get(
        s.llm_provider, "")


def is_configured() -> bool:
    return bool(_api_key())


def model_name() -> str:
    return get_settings().llm_model


def get_llm():
    """Return a LangChain chat model. Raises AINotConfigured when there is no API key."""
    s = get_settings()
    key = _api_key()
    if not key:
        raise AINotConfigured()
    common = {"temperature": 0.2, "timeout": s.llm_timeout_seconds, "max_retries": 1}
    try:
        if s.llm_provider == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(model=s.llm_model, google_api_key=key, **common)
        if s.llm_provider == "anthropic":
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(model=s.llm_model, api_key=key, **common)
        if s.llm_provider == "openai":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(model=s.llm_model, api_key=key, **common)
    except ImportError as exc:
        raise AIError(f"The package for LLM_PROVIDER={s.llm_provider} is not installed: {exc.name}") from exc
    raise AIError(f"Unknown LLM_PROVIDER '{s.llm_provider}'. Use gemini, anthropic or openai.")
