"""Connect to DeepSeek and Supabase and build the planning graph."""
import os

from langchain_deepseek import ChatDeepSeek
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from supabase import acreate_client

from .graph import build


async def open_graph():
    """Connect to DeepSeek and Supabase and build the graph. Its progress is saved in Supabase (schema langgraph)."""
    llm = ChatDeepSeek(model=os.environ.get("PLANNING_MODEL", "deepseek-chat"), api_key=os.environ["DEEPSEEK_API_KEY"],
                       temperature=0, max_tokens=8192, timeout=180, max_retries=3)
    db = await acreate_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

    async def use_langgraph_schema(conn):
        await conn.execute("set search_path to langgraph")

    # Long model calls leave connections idle for minutes and Supabase's pooler may close them: test each connection
    # before use, drop idle ones early, and keep the TCP connection alive.
    pool = AsyncConnectionPool(os.environ["DATABASE_URL"], open=False, configure=use_langgraph_schema,
                               check=AsyncConnectionPool.check_connection, max_idle=60,
                               kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row,
                                       "keepalives": 1, "keepalives_idle": 30, "keepalives_interval": 10})
    await pool.open()
    saver = AsyncPostgresSaver(pool)
    await saver.setup()
    return build(llm, db, saver)
