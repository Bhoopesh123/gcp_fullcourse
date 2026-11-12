
import os
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------
# 1. Streamlit Configuration
# ---------------------------------------

st.set_page_config(
    page_title="OpenAI + Arize Phoenix",
    page_icon="🤖",
    layout="centered"
)

# ---------------------------------------
# 2. Phoenix OpenTelemetry Registration
# ---------------------------------------

from phoenix.otel import register

@st.cache_resource
def setup_phoenix():

    tracer_provider = register(
        project_name=os.getenv("PHOENIX_PROJECT", "test-eval"),
        endpoint=os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://136.80.194.201:4317"),
        protocol="grpc",
        api_key=os.getenv("PHOENIX_API_KEY"),
        auto_instrument=True,
        batch=os.getenv("PHOENIX_BATCH_EXPORT", "true").lower() == "true"
    )

    return tracer_provider


tracer_provider = setup_phoenix()

# ---------------------------------------
# 3. OpenAI import AFTER Phoenix register
# ---------------------------------------

import openai

client = openai.OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

# ---------------------------------------
# 4. Chatbot UI
# ---------------------------------------

st.title("🤖 OpenAI Chatbot")

st.caption(
    "Powered by GPT-4o-mini | Observed by Arize Phoenix"
)

# ---------------------------------------
# 5. Initialize Chat History
# ---------------------------------------

if "messages" not in st.session_state:

    st.session_state.messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful AI assistant. "
                "Give clear and concise answers."
            )
        }
    ]

# ---------------------------------------
# 6. Display Chat History
# ---------------------------------------

for message in st.session_state.messages:

    if message["role"] == "system":
        continue

    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# ---------------------------------------
# 7. User Input
# ---------------------------------------

user_input = st.chat_input("Ask me anything...")

if user_input:

    st.session_state.messages.append({
        "role": "user",
        "content": user_input
    })

    with st.chat_message("user"):
        st.markdown(user_input)

    # -----------------------------------
    # 8. OpenAI LLM Call
    # -----------------------------------

    with st.chat_message("assistant"):

        with st.spinner("Thinking..."):

            try:

                response = client.chat.completions.create(

                    model="gpt-4o-mini",

                    messages=st.session_state.messages,

                    temperature=0.7

                )

                answer = response.choices[0].message.content

                st.markdown(answer)

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": answer
                })

                # Token information
                if response.usage:

                    st.caption(
                        f"Input tokens: {response.usage.prompt_tokens} | "
                        f"Output tokens: {response.usage.completion_tokens} | "
                        f"Total tokens: {response.usage.total_tokens}"
                    )

            except Exception as e:

                st.error(f"OpenAI API Error: {str(e)}")

# ---------------------------------------
# 9. Sidebar
# ---------------------------------------

with st.sidebar:

    st.header("Observability")

    st.success("Phoenix instrumentation initialized")

    st.write(f"**Project:** {os.getenv('PHOENIX_PROJECT', 'test-eval')}")

    st.write("**LLM:** gpt-4o-mini")

    st.write(f"**Collector:** {os.getenv('PHOENIX_COLLECTOR_ENDPOINT', 'http://136.80.194.201:4317')} (gRPC)")

    if st.button("Clear conversation"):

        st.session_state.messages = [
            {
                "role": "system",
                "content": "You are a helpful AI assistant."
            }
        ]

        st.rerun()
