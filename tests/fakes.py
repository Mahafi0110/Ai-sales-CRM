"""Pretend AI models for tests. They give scripted answers and remember what they were asked."""
import json

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

GOOD_QUALIFY = {
    "score": 82, "recommended_status": "qualified", "summary": "Strong fit with a clear need.",
    "strengths": ["Has budget"], "gaps": ["No decision maker named"], "next_actions": ["Book a demo", "Send pricing"],
}
GOOD_EMAIL = {"subject": "Following up on our chat", "body": "Hi Priya,\n\nThanks for your time.\n\nBest,\nRiya Rep"}


class RecordingFake(FakeListChatModel):
    """Gives scripted text answers (for the single-prompt AI features)."""
    seen: list = Field(default_factory=list)

    def _call(self, messages, *args, **kwargs):
        self.seen.append("\n".join(str(m.content) for m in messages))
        return super()._call(messages, *args, **kwargs)


class BrokenFake(FakeListChatModel):
    message: str = "boom"

    def _call(self, messages, *args, **kwargs):
        raise RuntimeError(self.message)


class ScriptedChat(BaseChatModel):
    """A pretend tool-calling model: plays back a list of AIMessages, one per call."""
    script: list = Field(default_factory=list)
    seen: list = Field(default_factory=list)
    calls: int = 0
    repeat_last: bool = False
    fail_with: str = ""

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(list(messages))
        if self.fail_with:
            raise RuntimeError(self.fail_with)
        index = min(self.calls, len(self.script) - 1) if self.repeat_last else self.calls
        self.calls += 1
        # A real model makes a brand-new message every time (LangGraph merges messages that share an id).
        message = self.script[index].model_copy(update={"id": None})
        return ChatResult(generations=[ChatGeneration(message=message)])


def tool_call(name: str, args: dict | None = None, call_id: str = "c1", *extra: tuple) -> AIMessage:
    """An AI message asking to use one or more tools. extra = more (name, args, id) tuples."""
    calls = [(name, args or {}, call_id), *extra]
    return AIMessage(content="", tool_calls=[{"name": n, "args": a, "id": i, "type": "tool_call"} for n, a, i in calls])


def final(text: str) -> AIMessage:
    return AIMessage(content=text)


def dumps(data) -> str:
    return json.dumps(data)


class ConceptEmbeddings:
    """A pretend embedding model. Words in the same group count as the same idea (so 'cost' matches 'fee'),
    which lets tests show search-by-meaning without a real AI service."""

    GROUPS = [
        {"price", "pricing", "cost", "fee", "fees", "charge", "pay", "payment", "cheap", "expensive", "dollar"},
        {"contract", "agreement", "terms", "commitment", "legal", "cancel", "cancellation"},
        {"demo", "trial", "preview", "walkthrough", "sample"},
        {"support", "help", "assist", "assistance", "service"},
        {"discount", "offer", "deal", "promotion", "savings"},
        {"security", "privacy", "encryption", "compliance", "gdpr"},
    ]
    SIZE = 16

    def __init__(self, fail_on_call: int | None = None, fail_always: bool = False):
        self.calls: list[int] = []  # size of each batch asked for
        self.queries: list[str] = []
        self.fail_on_call = fail_on_call
        self.fail_always = fail_always

    def _vector(self, text: str) -> list[float]:
        import re
        vector = [0.0] * self.SIZE
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            for index, group in enumerate(self.GROUPS):
                if word in group:
                    vector[index] += 1.0
                    break
            else:
                vector[len(self.GROUPS) + sum(map(ord, word)) % (self.SIZE - len(self.GROUPS))] += 0.1
        return vector

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(len(texts))
        if self.fail_always or (self.fail_on_call is not None and len(self.calls) == self.fail_on_call):
            raise RuntimeError("429 RESOURCE_EXHAUSTED quota")
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        if self.fail_always:
            raise RuntimeError("embedding service down")
        return self._vector(text)
