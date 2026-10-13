"""Runs one prompt through the model and turns the answer into a checked Python object."""
import json
import logging
from typing import TypeVar

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, ValidationError

from app.ai.errors import AIBusy, AIError

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


def extract_json(text: str) -> dict:
    """Models sometimes wrap JSON in ```json fences or add a sentence around it; take the {...} part."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in the answer")
    return json.loads(text[start:end + 1])


def translate_error(exc: Exception) -> AIError:
    text = str(exc).lower()
    log.exception("AI call failed")
    if any(word in text for word in ("429", "resource_exhausted", "quota", "rate limit", "rate_limit")):
        return AIBusy()
    if any(word in text for word in ("api key", "api_key", "401", "403", "permission", "unauthenticated")):
        return AIError("The AI key was rejected. Check GOOGLE_API_KEY (or the key for your provider) in .env.")
    if any(word in text for word in ("name or service not known", "connecterror", "connection error",
                                     "timed out", "timeout", "temporary failure")):
        return AIError("Could not reach the AI service. Check your internet connection and try again.")
    if "404" in text and "model" in text:
        return AIError("The AI model name was not found. Update LLM_MODEL in .env with a current model name.")
    return AIError()


def run_json(llm, system: str, human: str, variables: dict, result_model: type[T], retries: int = 1) -> T:
    """Ask the model, check the answer. If the answer is unreadable, ask once more."""
    chain = ChatPromptTemplate.from_messages([("system", system), ("human", human)]) | llm | StrOutputParser()
    for attempt in range(retries + 1):
        try:
            text = chain.invoke(variables)
        except Exception as exc:  # network, quota, bad key... all become friendly errors
            raise translate_error(exc) from exc
        try:
            return result_model.model_validate(extract_json(text))
        except (ValueError, ValidationError) as exc:
            log.warning("AI answer was not usable (attempt %s): %s", attempt + 1, exc)
    raise AIError("The AI answered in a form I could not read. Please try again.")
