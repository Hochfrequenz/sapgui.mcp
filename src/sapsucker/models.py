"""Pydantic data models for SAP GUI element information."""

from __future__ import annotations

from pydantic import BaseModel

__all__ = ["ElementInfo", "SessionInfo"]


class SessionInfo(BaseModel):
    """Structured information about a SAP GUI session."""

    system_name: str
    client: str
    user: str
    language: str
    transaction: str
    program: str
    screen_number: int
    application_server: str
    response_time: int
    round_trips: int


class ElementInfo(BaseModel):
    """Structured information about a SAP GUI element and its children."""

    id: str
    type: str
    type_as_number: int
    name: str
    text: str
    changeable: bool
    children: list[ElementInfo] = []
