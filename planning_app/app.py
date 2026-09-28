"""Streamlit chat for the planning graph. Run from this folder:  streamlit run app.py"""
import asyncio
import os
import threading
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from langgraph.types import Command

HERE = Path(__file__).parent
load_dotenv(HERE / ".env")
load_dotenv(HERE.parent / ".env")  # the project's existing .env one folder up

from graph import open_graph  # noqa: E402  (needs the env loaded first)
from steps import ORDER, STEPS  # noqa: E402

NEEDED = ["DEEPSEEK_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_DB_URL", "PROJECT_ID", "PM_USER_ID"]

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

    return run(open_graph()), run


graph, run = runtime()
config = {"configurable": {"thread_id": os.environ["PROJECT_ID"]}, "recursion_limit": 200}


def send(value):
    with st.spinner("Working..."):
        try:
            run(graph.ainvoke(value, config))
        except Exception as e:  # the last saved progress is kept; show the error and let the PM try again
            st.session_state.error = f"{type(e).__name__}: {e}"
    st.rerun()


snapshot = run(graph.aget_state(config))
values = snapshot.values
pending = snapshot.interrupts[0].value if snapshot.interrupts else None
approved = values.get("approved", {})

# ---- sidebar: where the plan stands (read-only) ---------------------------------------------------------------
with st.sidebar:
    st.header("Plan")
    for name in ORDER:
        status = ("working" if values.get("step") == name and pending
                  else f"approved v{approved[name]['version']}" if name in approved else "not started")
        with st.expander(f"{STEPS[name].title} — {status}"):
            st.markdown(approved[name]["report"] if name in approved else "_Nothing approved yet._")
    if values.get("change"):
        st.info(f"Applying a change to {STEPS[values['change']['origin']].title}.")

# ---- main: one chat for every agent ------------------------------------------------------------------------------
st.title("Planning")
if err := st.session_state.pop("error", None):
    st.error(err)

if not values:
    if idea := st.chat_input("Describe your project idea to start"):
        send({"project_id": os.environ["PROJECT_ID"], "pm_id": os.environ["PM_USER_ID"], "idea": idea})
    st.stop()

chat = list(values.get("log", []))
if pending and pending["type"] == "question":  # the running agent's messages that are not in the log yet
    seen = values.get("logged", {}).get(pending["step"], 0)
    chat += [{"step": pending["step"], **m} for m in pending["chat"][seen:]]

part = "start"
for m in chat:
    if m["step"] != part:  # a small divider when another part of the plan takes over
        part = m["step"]
        st.caption(f"— {STEPS[part].title if part else 'Plan complete'} —")
    st.chat_message(m["role"]).markdown(m["text"])

failed = next((t.error for t in snapshot.tasks if t.error), None)
if failed or not pending:  # a step failed (for example the model API): nothing is lost, run it again
    st.error(f"Something went wrong: {failed}" if failed else "The planning graph stopped without waiting for you.")
    if st.button("Try again", type="primary"):
        send(None)
    st.stop()

if pending["type"] == "review":
    if pending["step"] != part:
        st.caption(f"— {STEPS[pending['step']].title} —")
    with st.chat_message("assistant"):
        st.markdown(pending["text"])
        if st.button("Approve", type="primary"):
            send(Command(resume=True))
elif pending["type"] == "idle":
    st.chat_message("assistant").markdown(pending["text"])

placeholder = "Approve above, or say what to change" if pending["type"] == "review" else "Your message"
if message := st.chat_input(placeholder):
    send(Command(resume=message))
