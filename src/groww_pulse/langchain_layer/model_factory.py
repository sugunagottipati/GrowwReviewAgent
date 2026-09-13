import json
from typing import Any, TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from groww_pulse.config.settings import Settings

T = TypeVar("T", bound=BaseModel)


class FakeStructuredChatModel(BaseChatModel):
    """A configurable fake chat model for deterministic testing and dry-run mode."""

    responses: list[str] = ["{}"]
    call_count: int = 0
    recorded_inputs: list[list[BaseMessage]] = []

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> Any:
        from langchain_core.outputs import ChatGeneration, ChatResult

        self.call_count += 1
        self.recorded_inputs.append(messages)
        response_text = self.responses[(self.call_count - 1) % len(self.responses)]
        msg = AIMessage(content=response_text)
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def with_structured_output(
        self,
        schema: type[T] | dict[str, Any],
        **kwargs: Any,
    ) -> Runnable[Any, Any]:
        """Return a runnable that parses responses into the target Pydantic schema."""

        def _parse(input_val: Any) -> Any:
            # Generate response via standard chat model generate
            if isinstance(input_val, list):
                messages = input_val
            elif hasattr(input_val, "to_messages"):
                messages = input_val.to_messages()
            else:
                messages = [AIMessage(content=str(input_val))]

            chat_result = self._generate(messages)
            content = chat_result.generations[0].message.content

            if isinstance(schema, type) and issubclass(schema, BaseModel):
                data = json.loads(content) if isinstance(content, str) else content
                return schema.model_validate(data)
            return content

        return RunnableLambda(_parse)

    @property
    def _llm_type(self) -> str:
        return "fake-structured-chat-model"


def get_chat_model(
    settings: Settings | None = None,
    override_model: BaseChatModel | None = None,
) -> BaseChatModel:
    """Model factory returning a configured BaseChatModel instance."""
    if override_model is not None:
        return override_model

    active_settings = settings or Settings()

    if active_settings.dry_run or active_settings.model_provider.lower() == "fake":
        return FakeStructuredChatModel()

    provider = active_settings.model_provider.lower()
    if provider == "openai":
        return ChatOpenAI(
            model=active_settings.model_id,
            temperature=active_settings.model_temperature,
            timeout=float(active_settings.timeout_seconds),
        )

    if provider == "groq":
        # Throttle to the provider's requests-per-minute cap (e.g., Groq free tier).
        rate_limiter = InMemoryRateLimiter(
            requests_per_second=active_settings.model_requests_per_minute / 60.0,
            check_every_n_seconds=0.1,
            max_bucket_size=1,
        )
        return ChatGroq(
            model_name=active_settings.model_id,
            temperature=active_settings.model_temperature,
            timeout=float(active_settings.timeout_seconds),
            rate_limiter=rate_limiter,
        )

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=active_settings.model_id,
            temperature=active_settings.model_temperature,
            timeout=float(active_settings.timeout_seconds),
        )

    raise ValueError(f"Unsupported model provider: '{active_settings.model_provider}'")
