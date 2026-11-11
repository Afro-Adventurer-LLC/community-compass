from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..config import (
    BEDROCK_MODEL_ID,
    DEFAULT_EVENT_YEAR,
    GENERATOR_MODE,
    LLM_TIMEOUT_S,
    deploy_git_sha,
    use_aws,
)
from ..models.schemas import ChatIn, FeedbackIn, UnansweredIn
from ..services.chat import chat
from ..services.generator import get_generator
from ..services.retrieval import get_retriever
from ..services.store import ConversationForbidden, ConversationNotFound, get_store

router = APIRouter()


def _conv_errors(fn):
    try:
        return fn()
    except ConversationNotFound:
        raise HTTPException(404, "Unknown conversation: start a new chat")
    except ConversationForbidden:
        raise HTTPException(403, "This conversation belongs to a different profile: start a new chat")


@router.get("/health")
def health():
    retriever = get_retriever()
    store = get_store()
    n_docs = len(getattr(getattr(retriever, "index", None), "docs", []) or [])
    n_chunks = len(getattr(getattr(retriever, "index", None), "chunks", []) or [])
    return dict(
        status="ok",
        mock=not use_aws(),
        retriever=retriever.name,
        knowledge_base=use_aws() and retriever.name == "bedrock",
        documents=n_docs,
        chunks=n_chunks,
        default_generator=get_generator(None).name,
        generator_mode=GENERATOR_MODE,
        llm_timeout_s=LLM_TIMEOUT_S,
        llm_configured=use_aws(),
        bedrock_model_id=BEDROCK_MODEL_ID if use_aws() else None,
        default_event_year=DEFAULT_EVENT_YEAR,
        unanswered=len(store.list_unanswered()),
        feedback=len(store.list_feedback()),
        git_sha=deploy_git_sha(),
    )


@router.post("/chat")
def chat_api(body: ChatIn):
    profile = dict(
        event_year=body.event_year or DEFAULT_EVENT_YEAR,
        include_alumni=body.include_alumni,
        role=body.role,
    )
    return _conv_errors(
        lambda: chat(
            body.question,
            profile,
            conversation_id=body.conversation_id,
            mode=body.mode,
        )
    )


@router.get("/chat/{conversation_id}")
def chat_get(conversation_id: str, role: str = "grantee", event_year: int = DEFAULT_EVENT_YEAR, include_alumni: bool = True):
    store = get_store()
    profile = dict(role=role, event_year=event_year, include_alumni=include_alumni)
    from ..services.chat import _profile_key

    def get():
        store.check(conversation_id, _profile_key(profile))
        return dict(conversation_id=conversation_id, turns=store.turns(conversation_id))

    return _conv_errors(get)


@router.post("/feedback")
def feedback_api(body: FeedbackIn):
    store = get_store()
    fid = store.add_feedback(body.model_dump())
    return dict(id=fid, ok=True)


@router.post("/unanswered")
def unanswered_api(body: UnansweredIn):
    store = get_store()
    uid = store.add_unanswered({**body.model_dump(), "source": "user_flag"})
    return dict(id=uid, ok=True)


@router.get("/advisor/unanswered")
def advisor_unanswered():
    return dict(items=get_store().list_unanswered())


@router.get("/advisor/feedback")
def advisor_feedback():
    return dict(items=get_store().list_feedback())
