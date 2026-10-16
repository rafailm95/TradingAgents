"""Opt-in fail-closed completion checks; not a factual accuracy certificate."""

from langchain_core.callbacks import BaseCallbackHandler


class OutputQualityError(RuntimeError):
    """A response cannot safely be passed to another workflow stage."""


def ensure_complete(message, generation_info=None):
    """Require a documented successful stop and a nonempty, valid response.

    Unknown provider metadata fails closed in strict mode. This intentionally
    supports only providers exposing one of these explicit stop reasons.
    """
    metadata = {**(generation_info or {}), **(message.response_metadata or {})}
    reason = metadata.get("finish_reason") or metadata.get("stop_reason")
    if reason not in {"stop", "tool_calls", "end_turn", "tool_use", "stop_sequence"}:
        raise OutputQualityError(f"Unconfirmed or incomplete model output: {reason!r}")
    if message.invalid_tool_calls:
        raise OutputQualityError("Invalid model tool call")
    if message.additional_kwargs.get("refusal"):
        raise OutputQualityError("Model refused the request")
    if not message.content and not message.tool_calls:
        raise OutputQualityError("Empty model response")


class CompletionGuard(BaseCallbackHandler):
    """Raise before LangChain hands a response to its downstream consumer."""

    raise_error = True

    def on_llm_end(self, response, **kwargs):
        if not response.generations or any(not batch for batch in response.generations):
            raise OutputQualityError("Missing model generations")
        for batch in response.generations:
            for generation in batch:
                ensure_complete(generation.message, generation.generation_info)
