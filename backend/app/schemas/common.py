"""Shared pagination, envelope and filter schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PaginationParams(BaseModel):
    page: int = Field(1, ge=1, description="1-based page index")
    page_size: int = Field(20, ge=1, le=1000, description="Items per page (max 1000)")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


class PageMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int
    has_next: bool
    has_previous: bool


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    meta: PageMeta

    @classmethod
    def build(cls, items: list[T], total: int, page: int, page_size: int) -> PaginatedResponse[T]:
        total_pages = (total + page_size - 1) // page_size if page_size else 0
        return cls(
            items=items,
            meta=PageMeta(
                page=page,
                page_size=page_size,
                total=total,
                total_pages=total_pages,
                has_next=page < total_pages,
                has_previous=page > 1,
            ),
        )


class ErrorDetail(BaseModel):
    code: str = Field(..., examples=["not_found"])
    message: str = Field(..., examples=["The requested resource does not exist."])
    details: object | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
    request_id: str | None = None
    timestamp: datetime


class MessageResponse(BaseModel):
    message: str
