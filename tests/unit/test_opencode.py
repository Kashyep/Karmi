import json

import httpx
import pytest

from daily_agent.opencode import (
    FREE_MODEL_BY_ID,
    PRIVATE_DATA_MODEL_IDS,
    OpenCodeError,
    chat_completion,
    fetch_catalog,
)


def test_catalog_is_intersected_with_dated_free_allowlist() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            json={"object": "list", "data": [{"id": "space-bunny-free"}, {"id": "gpt-6-astra"}]},
        )
    )
    catalog = fetch_catalog(api_key="private-key", transport=transport)
    assert catalog == {"space-bunny-free", "gpt-6-astra"}
    assert "space-bunny-free" in FREE_MODEL_BY_ID
    assert "gpt-6-astra" not in FREE_MODEL_BY_ID
    assert {
        "space-bunny-free",
        "longcat-2.5-preview-free",
        "step-5-preview-free",
    } == PRIVATE_DATA_MODEL_IDS


def test_chat_completion_posts_only_bounded_plain_text_and_reports_usage() -> None:
    seen: dict[str, object] = {}

    def respond(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": "A useful draft."}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 23, "completion_tokens": 5},
            },
        )

    completion = chat_completion(
        api_key="private-key",
        model_id="space-bunny-free",
        messages=[{"role": "user", "content": "Write a short greeting."}],
        max_output_tokens=128,
        transport=httpx.MockTransport(respond),
    )

    assert completion.text == "A useful draft."
    assert completion.model_id == "space-bunny-free"
    assert completion.input_tokens == 23
    assert completion.output_tokens == 5
    assert completion.cost_micro == 0
    assert seen["url"] == "https://opencode.ai/zen/v1/chat/completions"
    assert seen["auth"] == "Bearer private-key"
    assert seen["payload"] == {
        "model": "space-bunny-free",
        "messages": [{"role": "user", "content": "Write a short greeting."}],
        "max_tokens": 128,
        "temperature": 0.2,
        "stream": False,
    }


@pytest.mark.parametrize(
    ("model_id", "messages", "max_output_tokens"),
    [
        ("gpt-6-astra", [{"role": "user", "content": "hello"}], 10),
        ("space-bunny-free", [{"role": "tool", "content": "hello"}], 10),
        ("space-bunny-free", [{"role": "user", "content": "hello"}], 0),
    ],
)
def test_chat_completion_rejects_unapproved_model_or_unbounded_input(
    model_id: str, messages: list[dict[str, str]], max_output_tokens: int
) -> None:
    with pytest.raises(OpenCodeError):
        chat_completion(
            api_key="private-key",
            model_id=model_id,
            messages=messages,
            max_output_tokens=max_output_tokens,
        )


def test_catalog_failure_fails_closed() -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(503))
    with pytest.raises(OpenCodeError, match="catalog is unavailable"):
        fetch_catalog(api_key="private-key", transport=transport)
