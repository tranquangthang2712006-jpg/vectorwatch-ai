"""Trợ lý AI Agent (hỏi đáp) — POST /api/agent/chat và lịch sử hội thoại."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..agents import assistant
from ..security import current_user

router = APIRouter(prefix="/api/agent", tags=["agent"])


class ChatBody(BaseModel):
    message: str
    conversation_id: str | None = None
    context: dict | None = None


@router.post("/chat")
def chat(body: ChatBody, user: dict = Depends(current_user)):
    return assistant.chat(body.message, user, body.conversation_id, body.context)


@router.get("/suggestions")
def suggestions(user: dict = Depends(current_user)):
    return assistant.SUGGESTIONS


@router.get("/conversations")
def conversations(user: dict = Depends(current_user)):
    return assistant.conversations(user)


@router.get("/conversations/{conversation_id}")
def conversation(conversation_id: str, user: dict = Depends(current_user)):
    return assistant.history(conversation_id, user)
