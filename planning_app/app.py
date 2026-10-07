"""Streamlit chat for the planning graph (the test screen). Run from this folder:  streamlit run app.py

Only drawing lives here; the planning itself is the `planning` package (planning/service.py drives it)."""
import asyncio
import os
import queue
import threading
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

HERE = Path(__file__).parent
load_dotenv(HERE / ".env")
load_dotenv(HERE.parent / ".env")  # the project's existing .env one folder up

from planning import service  # noqa: E402  (needs the env loaded first)
from planning.connections import open_graph  # noqa: E402
from planning.steps import STEPS  # noqa: E402

NEEDED = ["DEEPSEEK_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "DATABASE_URL", "PROJECT_ID", "PM_USER_ID"]

st.set_page_config(page_title="Planning", page_icon=":clipboard:", layout="wide")
if missing := [n for n in NEEDED if not os.environ.get(n)]:
    st.error(f"Missing in .env: {', '.join(missing)} (see .env.example).")
    st.stop()


@st.cache_resource(show_spinner="Connecting to DeepSeek and Supabase...")
def runtime():
    # One event loop for the whole app: the database pool lives on it. psycopg needs a selector loop on Windows.
    loop = asyncio.SelectorEventLoop()
    threading.Thread(target=loop.run_forever, daemon=True).start()

    def run(coro):
        return asyncio.run_coroutine_threadsafe(coro, loop).result()

    return run(open_graph()), run, loop


graph, run, loop = runtime()


def send(action, *args):
    """Run one service action, showing each change an agent writes while it works."""
    events = queue.Queue()
    done = asyncio.run_coroutine_threadsafe(action(graph, *args, on_step=events.put), loop)
    done.add_done_callback(lambda _: events.put(None))
    with st.status("Working...") as status:
        count = 0
        while (event := events.get()) is not None:
            count += 1
            status.update(label=f"{event} ({count} so far)...")
        try:
            done.result()
        except Exception as e:  # the last saved progress is kept; show the error and let the PM try again
            st.session_state.error = f"{type(e).__name__}: {e}"
    st.rerun()


def report(text, changes):
    """A review report. A later review of the same part shows what changed first, with the full report folded."""
    if changes is None:
        st.markdown(text)
        return
    st.markdown("**What changed:**\n" + ("\n".join(f"- {c}" for c in changes) or "- nothing since you last saw it"))
    with st.expander("Show the full report"):
        st.markdown(text)


now = run(service.status(graph))
pending = now["waiting"]

# ---- sidebar: where the plan stands (read-only) ---------------------------------------------------------------
with st.sidebar:
    st.header("Plan")
    for p in now["parts"]:
        st.markdown(f"**{p['title']}** — {p['status']}")
    if now["changing"]:
        st.info(f"Applying a change to {now['changing']}.")

# ---- main: one chat for every agent ------------------------------------------------------------------------------
st.title("Planning")
if err := st.session_state.pop("error", None):
    st.error(err)

if not now["started"]:
    if idea := st.chat_input("Describe your project idea to start"):
        send(service.start, idea)
    st.stop()

part = "start"
for m in now["chat"]:
    if m["step"] != part:  # a small divider when another part of the plan takes over
        part = m["step"]
        if part:  # messages from no part (check-ins, the closing message) get no divider
            st.caption(f"— {STEPS[part].title} —")
    with st.chat_message(m["role"]):
        report(m["text"], m.get("changes"))

if now["error"] or not pending:  # a step failed (for example the model API): nothing is lost, run it again
    st.error(f"Something went wrong: {now['error']}" if now["error"]
             else "The planning stopped unexpectedly. Nothing is lost.")
    if st.button("Try again", type="primary"):
        send(service.retry)
    st.stop()

if pending["type"] == "review":
    if pending["step"] != part:
        st.caption(f"— {STEPS[pending['step']].title} —")
    with st.chat_message("assistant"):
        report(pending["text"], pending.get("changes"))
        if st.button("Approve", type="primary"):
            send(service.approve)
elif pending["type"] == "idle":
    st.chat_message("assistant").markdown(pending["text"])

placeholder = "Approve above, or say what to change" if pending["type"] == "review" else "Your message"
if message := st.chat_input(placeholder):
    send(service.answer, message)
