"""Browser localStorage chat history persistence.

Uses a hidden Streamlit text_area as a bridge for JS→Python communication.
Save is fire-and-forget. Load uses DOM manipulation to write into a Streamlit widget.
"""
import json

import streamlit as st
import streamlit.components.v1 as components

STORAGE_KEY = "dbx_expert_chat_history"
SESSION_STORAGE_KEY = "dbx_expert_session_id"
MAX_PERSISTED_MESSAGES = 50
BRIDGE_KEY = "_ls_history_bridge"


def save_chat_to_local_storage(messages: list, session_id: str = ""):
    """Fire-and-forget save of chat messages to browser localStorage."""
    slim = []
    for message in messages[-MAX_PERSISTED_MESSAGES:]:
        entry = {"role": message.get("role", "assistant"), "content": message.get("content", "")}

        for field in ["raw_content", "topic", "intent", "answer_mode", "question"]:
            if message.get(field):
                entry[field] = message[field]

        if message.get("sources"):
            entry["sources"] = [
                (source[0], source[1], "") if isinstance(source, (list, tuple)) and len(source) >= 3 else source
                for source in message["sources"]
            ]

        slim.append(entry)

    components.html(
        f"""<script>
        try {{
            window.parent.localStorage.setItem("{STORAGE_KEY}", {json.dumps(json.dumps(slim))});
            window.parent.localStorage.setItem("{SESSION_STORAGE_KEY}", {json.dumps(session_id or "")});
        }} catch(e) {{ console.warn("localStorage save failed:", e); }}
        </script>""",
        height=1,
    )


def inject_history_loader():
    """Inject JS that reads localStorage and populates a hidden bridge widget."""
    if st.session_state.get("_ls_loaded"):
        return

    components.html(
        f"""<script>
        (function() {{
            if (window.parent.__dbxHistoryLoaderRan) return;
            window.parent.__dbxHistoryLoaderRan = true;

            const stored = window.parent.localStorage.getItem("{STORAGE_KEY}");
            if (!stored) return;

            try {{
                const messages = JSON.parse(stored);
                if (!messages || !messages.length) return;
            }} catch(e) {{
                return;
            }}

            const bridge = window.parent.document.querySelector('textarea[aria-label="{BRIDGE_KEY}"]');
            if (!bridge) return;

            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                window.parent.HTMLTextAreaElement.prototype,
                'value'
            ).set;
            nativeInputValueSetter.call(bridge, stored);
            bridge.dispatchEvent(new Event('input', {{ bubbles: true }}));
            bridge.dispatchEvent(new Event('change', {{ bubbles: true }}));
        }})();
        </script>""",
        height=1,
    )


def render_history_bridge():
    """Render the hidden bridge textarea that JS writes localStorage data into."""
    st.markdown(
        '<div style="position:absolute;left:-9999px;height:0;overflow:hidden;">',
        unsafe_allow_html=True,
    )
    st.text_area(
        BRIDGE_KEY,
        key=BRIDGE_KEY,
        value="",
        label_visibility="collapsed",
        height=1,
    )
    st.markdown('</div>', unsafe_allow_html=True)


def try_restore_from_local_storage() -> list:
    """Check if the bridge has data and return parsed messages, or empty list."""
    bridge_value = st.session_state.get(BRIDGE_KEY, "")
    if not bridge_value or bridge_value.strip() == "":
        return []

    try:
        messages = json.loads(bridge_value)
        if isinstance(messages, list) and messages:
            st.session_state[BRIDGE_KEY] = ""
            st.session_state["_ls_loaded"] = True
            return messages
    except (json.JSONDecodeError, TypeError):
        pass

    return []


def clear_local_storage():
    """Render a component that clears the chat history from localStorage."""
    components.html(
        f"""<script>
        window.parent.localStorage.removeItem("{STORAGE_KEY}");
        window.parent.localStorage.removeItem("{SESSION_STORAGE_KEY}");
        window.parent.__dbxHistoryLoaderRan = false;
        </script>""",
        height=1,
    )
