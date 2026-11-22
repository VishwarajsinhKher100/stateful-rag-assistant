import uuid

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from .auth_utils import hash_password, verify_password
from .database import Base, SessionLocal, engine
from .models import ChatMessage, User


def initialize_database() -> None:
    Base.metadata.create_all(bind=engine)


def sign_up(name: str, email: str, password: str) -> User:
    name = name.strip()
    email = email.strip().lower()
    if not name or len(name) > 100:
        raise ValueError("Name must contain between 1 and 100 characters.")
    if len(email) < 5 or len(email) > 255 or "@" not in email:
        raise ValueError("Enter a valid email address.")
    if len(password) < 6 or len(password) > 100:
        raise ValueError("Password must contain between 6 and 100 characters.")

    with SessionLocal() as db:
        if db.query(User).filter(User.email == email).first():
            raise ValueError("Email is already registered.")
        user = User(name=name, email=email, hashed_password=hash_password(password))
        db.add(user)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ValueError("Email is already registered.") from exc
        db.refresh(user)
        return user


def sign_in(email: str, password: str) -> User:
    email = email.strip().lower()
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).first()
        if not user or not verify_password(password, user.hashed_password):
            raise ValueError("Invalid email or password.")
        return user


def list_sessions(email: str) -> list[dict[str, str]]:
    with SessionLocal() as db:
        rows = (
            db.query(
                ChatMessage.session_id,
                func.min(ChatMessage.created_at).label("first_created"),
                func.min(ChatMessage.content).label("first_content"),
            )
            .filter(ChatMessage.user_email == email)
            .group_by(ChatMessage.session_id)
            .order_by(func.min(ChatMessage.created_at).desc())
            .all()
        )
        return [
            {
                "session_id": row.session_id,
                "title": (
                    row.first_content[:30] + "..."
                    if len(row.first_content) > 30
                    else row.first_content
                ),
                "created_at": row.first_created.isoformat(),
            }
            for row in rows
        ]


def get_session_history(email: str, session_id: str) -> list[dict[str, str]]:
    with SessionLocal() as db:
        messages = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.session_id == session_id,
                ChatMessage.user_email == email,
            )
            .order_by(ChatMessage.created_at.asc())
            .all()
        )
        if not messages:
            raise ValueError("Chat session not found.")
        return [{"role": msg.role, "content": msg.content} for msg in messages]


def send_chat_message(
    email: str, session_id: str | None, message: str
) -> tuple[str, str]:
    message = message.strip()
    if not message or len(message) > 20000:
        raise ValueError("Message must contain between 1 and 20,000 characters.")
    active_session_id = session_id or str(uuid.uuid4())

    with SessionLocal() as db:
        existing_message = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == active_session_id)
            .first()
        )
        if existing_message and existing_message.user_email != email:
            raise ValueError("Chat session not found.")

        db.add(
            ChatMessage(
                session_id=active_session_id,
                user_email=email,
                role="user",
                content=message,
            )
        )
        db.commit()

    from .graph import GraphState, graph
    from langchain_core.messages import HumanMessage

    result = graph.invoke(
        GraphState(messages=[HumanMessage(content=message)]),
        config={"configurable": {"thread_id": active_session_id}},
    )
    reply = result["messages"][-1].content
    if not isinstance(reply, str):
        reply = str(reply)

    with SessionLocal() as db:
        db.add(
            ChatMessage(
                session_id=active_session_id,
                user_email=email,
                role="assistant",
                content=reply,
            )
        )
        db.commit()

    return active_session_id, reply
