"""AI problems, written as errors a person can understand. They are HTTPExceptions, so the API and the pages
both show the message without extra code."""
from fastapi import HTTPException, status


class AIError(HTTPException):
    def __init__(self, detail: str = "The AI service had a problem. Please try again in a moment.",
                 status_code: int = status.HTTP_502_BAD_GATEWAY):
        super().__init__(status_code, detail)


class AINotConfigured(AIError):
    def __init__(self, detail: str = "AI is not set up yet. Add GOOGLE_API_KEY to your .env file and restart."):
        super().__init__(detail, status.HTTP_503_SERVICE_UNAVAILABLE)


class AIBusy(AIError):
    def __init__(self):
        super().__init__("The AI usage limit was reached. Wait about a minute and try again.",
                         status.HTTP_429_TOO_MANY_REQUESTS)
