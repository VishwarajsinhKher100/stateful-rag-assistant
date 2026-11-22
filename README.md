# ConvoRAG

ConvoRAG is a document-aware chat assistant built as a single Python project. Its
Streamlit interface handles account sign-in, chat history, and PDF uploads; the
Python package provides authentication, chat persistence, retrieval, and the
LangGraph/Groq integration.

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- A Groq API key

The app uses a local SQLite database by default and stores PDF embeddings in a
local `chroma_db` directory. Both are created when needed. To use PostgreSQL,
set `DATABASE_URL` to a SQLAlchemy PostgreSQL URL.

## Setup

```powershell
uv python install 3.12
uv sync
```

`uv sync` creates the project `.venv` and installs the pinned dependencies from
`uv.lock`.

Create a `.env` file in the project root:

```env
GROQ_API_KEY=your_groq_api_key
# Optional: PostgreSQL instead of the default local SQLite database
# DATABASE_URL=postgresql://username:password@localhost:5432/chatbot_db
```

Start the application:

```powershell
uv run streamlit run app.py
```

Open the local URL printed by Streamlit, create an account, and start a chat.
Upload a PDF in the sidebar to use its contents as context for that chat.

The first chat or PDF upload downloads the `all-MiniLM-L6-v2` embedding model.