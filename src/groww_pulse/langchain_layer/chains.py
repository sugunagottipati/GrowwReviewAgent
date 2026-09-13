from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import Runnable

from groww_pulse.domain.models import PulseDraft, ThemeAnalysis
from groww_pulse.langchain_layer.model_factory import get_chat_model
from groww_pulse.langchain_layer.prompts.analysis_prompts import ANALYSIS_PROMPT_V1
from groww_pulse.langchain_layer.prompts.pulse_prompts import PULSE_PROMPT_V1


def create_analysis_chain(
    model: BaseChatModel | None = None,
    prompt_version: str = "v1.0",
) -> Runnable[dict[str, Any], Any]:
    """Create an LCEL chain for review theme analysis with structured output."""
    chat_model = model or get_chat_model()

    if prompt_version == "v1.0":
        prompt = ANALYSIS_PROMPT_V1
    else:
        raise ValueError(f"Unknown analysis prompt version: {prompt_version}")

    structured_model = chat_model.with_structured_output(ThemeAnalysis)
    return prompt | structured_model


def create_pulse_chain(
    model: BaseChatModel | None = None,
    prompt_version: str = "v1.0",
) -> Runnable[dict[str, Any], Any]:
    """Create an LCEL chain for weekly pulse draft generation with structured output."""
    chat_model = model or get_chat_model()

    if prompt_version == "v1.0":
        prompt = PULSE_PROMPT_V1
    else:
        raise ValueError(f"Unknown pulse prompt version: {prompt_version}")

    structured_model = chat_model.with_structured_output(PulseDraft)
    return prompt | structured_model
