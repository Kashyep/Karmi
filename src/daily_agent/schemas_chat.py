from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class FinishReason(StrEnum):
    STOP = "stop"
    LENGTH = "length"
    CONTENT_FILTER = "content_filter"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"
    ERROR = "error"


class MessageStatus(StrEnum):
    COMPLETE = "complete"
    STREAMING = "streaming"
    STOPPED = "stopped"
    INTERRUPTED = "interrupted"
    FAILED = "failed"


class ErrorCategory(StrEnum):
    QUOTA_EXHAUSTED = "quota_exhausted"
    CAPACITY_FULL = "capacity_full"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    VALIDATION_FAILED = "validation_failed"
    UNAUTHORIZED = "unauthorized"
    RESUME_UNAVAILABLE = "resume_unavailable"
    INTERNAL = "internal"
    NETWORK = "network"


class TitleSource(StrEnum):
    AUTO = "auto"
    USER = "user"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ChatBaseModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
    )

    def __getattr__(self, name: str) -> Any:
        # Allow accessing snake_case fields via camelCase aliases
        fields = self.__class__.model_fields
        for field_name, field_info in fields.items():
            if field_info.alias == name:
                return getattr(self, field_name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")


class ConversationView(ChatBaseModel):
    id: str
    title: str | None = None
    title_source: TitleSource | str = Field(default=TitleSource.AUTO, alias="titleSource")
    pinned: bool = False
    archived_at: datetime | None = Field(default=None, alias="archivedAt")
    updated_at: datetime = Field(alias="updatedAt")
    last_message_at: datetime | None = Field(default=None, alias="lastMessageAt")
    message_count: int = Field(default=0, alias="messageCount")


class ChatMessageView(ChatBaseModel):
    id: str
    conversation_id: str = Field(alias="conversationId")
    role: MessageRole | str
    status: MessageStatus | str
    content: str = ""
    finish_reason: FinishReason | str | None = Field(default=None, alias="finishReason")
    run_id: str | None = Field(default=None, alias="runId")
    parent_message_id: str | None = Field(default=None, alias="parentMessageId")
    variant_index: int = Field(default=0, alias="variantIndex")
    client_message_id: str | None = Field(default=None, alias="clientMessageId")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class ConversationPage(ChatBaseModel):
    items: list[ConversationView] = Field(default_factory=list)
    next_cursor: str | None = Field(default=None, alias="nextCursor")


class MessagePage(ChatBaseModel):
    items: list[ChatMessageView] = Field(default_factory=list)
    has_more_before: bool = Field(default=False, alias="hasMoreBefore")


class ConversationSearchResult(ChatBaseModel):
    conversation: ConversationView
    snippet: str
    matched: Literal["title", "content"]


class ChatStreamRequest(ChatBaseModel):
    conversation_id: str | None = Field(default=None, alias="conversationId")
    text: str = Field(min_length=1, max_length=100_000)
    client_message_id: str = Field(min_length=8, max_length=64, alias="clientMessageId")


class ConversationUpdate(ChatBaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    pinned: bool | None = None
    archived: bool | None = None


class StopResponse(ChatBaseModel):
    status: str = "cancelled"


# SSE Event Payloads


class RunStartedPayload(ChatBaseModel):
    run_id: str = Field(alias="runId")
    conversation_id: str = Field(alias="conversationId")
    user_message_id: str = Field(alias="userMessageId")
    assistant_message_id: str = Field(alias="assistantMessageId")
    seq: int = 0


class MessageDeltaPayload(ChatBaseModel):
    text: str


class HeartbeatPayload(ChatBaseModel):
    at: datetime


class RunFinishedPayload(ChatBaseModel):
    finish_reason: FinishReason | str = Field(alias="finishReason")
    outcome: str | None = None
    input_tokens: int | None = Field(default=None, alias="inputTokens")
    output_tokens: int | None = Field(default=None, alias="outputTokens")
    assistant_message_id: str | None = Field(default=None, alias="assistantMessageId")


class RunErrorPayload(ChatBaseModel):
    category: ErrorCategory | str
    retryable: bool
    retry_after_s: int | None = Field(default=None, alias="retryAfterS")
    assistant_message_id: str | None = Field(default=None, alias="assistantMessageId")
