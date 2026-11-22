import hashlib
import logging
import uuid

import streamlit as st

from convorag.services import (
    get_session_history,
    initialize_database,
    list_sessions,
    send_chat_message,
    sign_in,
    sign_up,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(page_title="ConvoRAG", page_icon=":material/chat:", layout="wide")

try:
    initialize_database()
except Exception as exc:
    st.error(f"Could not connect to the database: {exc}")
    st.stop()


def clear_chat() -> None:
    st.session_state.session_id = None
    st.session_state.messages = []
    st.session_state.attached_file_name = None


def show_authentication() -> None:
    st.title("ConvoRAG")
    st.caption("Chat with your documents and keep your conversations in one place.")
    mode = st.segmented_control(
        "Account", ["Sign in", "Create account"], default="Sign in", key="account_mode"
    )

    with st.form("authentication_form"):
        name = ""
        if mode == "Create account":
            name = st.text_input("Name", max_chars=100)
        email = st.text_input("Email", max_chars=255)
        password = st.text_input(
            "Password", type="password", max_chars=100, help="At least 6 characters."
        )
        submitted = st.form_submit_button(
            "Sign in" if mode == "Sign in" else "Create account",
            type="primary",
            width="stretch",
        )

    if not submitted:
        return
    if len(email.strip()) < 5 or len(password) < 6:
        st.error("Enter a valid email address and a password of at least 6 characters.")
        return
    if mode == "Create account" and not name.strip():
        st.error("Enter your name to create an account.")
        return

    try:
        user = (
            sign_in(email, password)
            if mode == "Sign in"
            else sign_up(name, email, password)
        )
    except ValueError as exc:
        st.error(str(exc))
        return
    except Exception:
        logger.exception("Authentication failed")
        st.error("Authentication failed. Check the database connection and try again.")
        return

    st.session_state.authenticated_email = user.email
    st.session_state.user_name = user.name
    clear_chat()
    st.rerun()


for key, default in {
    "authenticated_email": None,
    "messages": [],
    "session_id": None,
    "attached_file_name": None,
    "processed_pdf_signature": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

if not st.session_state.authenticated_email:
    show_authentication()
    st.stop()

email = st.session_state.authenticated_email
user_name = st.session_state.get("user_name", "User")

with st.sidebar:
    st.title("ConvoRAG")
    if st.button("New chat", icon=":material/add:", width="stretch"):
        clear_chat()
        st.rerun()

    st.subheader("Recent chats")
    try:
        sessions = list_sessions(email)
    except Exception as exc:
        st.error(f"Could not load chat history: {exc}")
        sessions = []

    for chat_session in sessions:
        if st.button(
            chat_session["title"],
            key=f"session-{chat_session['session_id']}",
            width="stretch",
            type=(
                "primary"
                if chat_session["session_id"] == st.session_state.session_id
                else "secondary"
            ),
        ):
            try:
                st.session_state.session_id = chat_session["session_id"]
                st.session_state.messages = get_session_history(
                    email, chat_session["session_id"]
                )
                st.session_state.attached_file_name = None
                st.rerun()
            except Exception as exc:
                st.error(f"Could not open this chat: {exc}")

    st.divider()
    st.subheader("Add a document")
    uploaded_file = st.file_uploader(
        "Upload a PDF for this chat",
        type=["pdf"],
        max_upload_size=20,
        help="PDF text is indexed for questions in the active chat.",
    )
    if uploaded_file is None:
        st.session_state.processed_pdf_signature = None
    else:
        file_bytes = uploaded_file.getvalue()
        signature = hashlib.sha256(file_bytes).hexdigest()
        if signature != st.session_state.processed_pdf_signature:
            target_session_id = st.session_state.session_id or str(uuid.uuid4())
            try:
                from convorag.rag_store import extract_and_store_pdf

                with st.spinner("Indexing PDF..."):
                    extract_and_store_pdf(file_bytes, target_session_id)
                st.session_state.session_id = target_session_id
                st.session_state.attached_file_name = uploaded_file.name
                st.session_state.processed_pdf_signature = signature
                st.success("PDF indexed for this chat.")
            except Exception as exc:
                logger.exception("PDF upload failed")
                st.error(f"Could not index the PDF: {exc}")

    if st.session_state.attached_file_name:
        st.caption(f"Attached: {st.session_state.attached_file_name}")
        if st.button(
            "Remove document",
            icon=":material/delete_outline:",
            width="stretch",
        ):
            try:
                from convorag.rag_store import delete_session_documents

                delete_session_documents(st.session_state.session_id)
                st.session_state.attached_file_name = None
                st.success("Document removed from this chat.")
                st.rerun()
            except Exception as exc:
                logger.exception("PDF removal failed")
                st.error(f"Could not remove the document: {exc}")

    st.divider()
    st.write(f"Signed in as **{user_name}**")
    if st.button("Log out", icon=":material/logout:", width="stretch"):
        for key in (
            "authenticated_email",
            "user_name",
            "session_id",
            "messages",
            "attached_file_name",
        ):
            st.session_state.pop(key, None)
        st.rerun()

st.title(f"What can I help you with, {user_name}?")
st.caption("Ask a question, or upload a PDF in the sidebar to chat with its contents.")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

prompt = st.chat_input("Message ConvoRAG", submit_mode="disable")
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    try:
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                session_id, reply = send_chat_message(
                    email,
                    st.session_state.session_id,
                    prompt,
                )
            st.markdown(reply)
        st.session_state.session_id = session_id
        st.session_state.messages.append({"role": "assistant", "content": reply})
        st.rerun()
    except Exception as exc:
        logger.exception("Chat response failed")
        st.error(f"Could not generate a response: {exc}")
