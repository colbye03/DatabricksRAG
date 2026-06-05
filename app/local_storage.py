"""Browser localStorage multi-chat persistence.

Uses a hidden Streamlit text_area as a bridge for JS-to-Python communication.
Save is fire-and-forget. Load uses DOM manipulation to write into a Streamlit widget.
"""
import json
import uuid
from datetime import datetime, timezone

import streamlit as st
import streamlit.components.v1 as components

STORAGE_KEY = "dbx_expert_chat_history"
SESSION_STORAGE_KEY = "dbx_expert_session_id"
SESSIONS_STORAGE_KEY = "dbx_expert_all_sessions"
MAX_PERSISTED_MESSAGES = 50
MAX_CHAT_SESSIONS = 20
MAX_SIDEBAR_SESSIONS = 10
BRIDGE_KEY = "_ls_history_bridge"
SESSIONS_BRIDGE_KEY = "_ls_sessions_bridge"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slim_messages(messages: list) -> list:
    slim = []
    for message in (messages or [])[-MAX_PERSISTED_MESSAGES:]:
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

    return slim


def build_chat_session_title(messages: list, fallback: str = "New chat") -> str:
    for message in messages or []:
        if message.get("role") != "user":
            continue

        content = (message.get("raw_content") or message.get("content") or "").strip()
        if not content:
            continue

        content = " ".join(content.split())
        return content[:40] + "..." if len(content) > 40 else content

    return fallback


def _normalize_session_record(session: dict):
    if not isinstance(session, dict):
        return None

    session_id = str(session.get("id", "")).strip()
    if not session_id:
        return None

    messages = session.get("messages") if isinstance(session.get("messages"), list) else []
    created_at = session.get("created_at") or session.get("updated_at") or _utc_now_iso()
    updated_at = session.get("updated_at") or created_at
    title = (session.get("title") or build_chat_session_title(messages)).strip() or "New chat"

    return {
        "id": session_id,
        "title": title,
        "messages": _slim_messages(messages),
        "created_at": created_at,
        "updated_at": updated_at,
    }


def _sort_sessions(sessions: list) -> list:
    return sorted(sessions, key=lambda session: session.get("updated_at") or "", reverse=True)


def _ensure_chat_sessions_state() -> list:
    sessions = st.session_state.get("chat_sessions", [])
    normalized = []
    seen_ids = set()

    if not isinstance(sessions, list):
        sessions = []

    for session in sessions:
        normalized_session = _normalize_session_record(session)
        if not normalized_session or normalized_session["id"] in seen_ids:
            continue
        seen_ids.add(normalized_session["id"])
        normalized.append(normalized_session)

    normalized = _sort_sessions(normalized)[:MAX_CHAT_SESSIONS]
    st.session_state["chat_sessions"] = normalized
    return normalized


def _upsert_current_session(messages: list, session_id: str) -> list:
    session_id = (session_id or "").strip()
    existing_sessions = _ensure_chat_sessions_state()
    existing_session = next((session for session in existing_sessions if session["id"] == session_id), None)
    slim_messages = _slim_messages(messages)
    sessions = [session for session in existing_sessions if session["id"] != session_id]

    if session_id and (slim_messages or existing_session):
        timestamp = _utc_now_iso()
        sessions.append(
            {
                "id": session_id,
                "title": build_chat_session_title(slim_messages, (existing_session or {}).get("title", "New chat")),
                "messages": slim_messages,
                "created_at": (existing_session or {}).get("created_at", timestamp),
                "updated_at": timestamp,
            }
        )

    sessions = _sort_sessions(sessions)[:MAX_CHAT_SESSIONS]
    st.session_state["chat_sessions"] = sessions
    return sessions


def _write_local_storage_payload(sessions: list, current_messages: list, session_id: str):
    components.html(
        f"""<script>
        try {{
            window.parent.localStorage.setItem("{SESSIONS_STORAGE_KEY}", {json.dumps(json.dumps(sessions))});
            window.parent.localStorage.setItem("{STORAGE_KEY}", {json.dumps(json.dumps(current_messages))});
            window.parent.localStorage.setItem("{SESSION_STORAGE_KEY}", {json.dumps(session_id or "")});
        }} catch(e) {{ console.warn("localStorage save failed:", e); }}
        </script>""",
        height=1,
    )


def save_chat_to_local_storage(messages: list, session_id: str = ""):
    """Fire-and-forget save of chat sessions to browser localStorage."""
    active_session_id = session_id or st.session_state.get("session_id", "")
    slim_messages = _slim_messages(messages)
    sessions = _upsert_current_session(messages, active_session_id)
    _write_local_storage_payload(sessions, slim_messages, active_session_id)


def inject_history_loader():
    """Inject JS that reads localStorage and populates hidden bridge widgets."""
    if st.session_state.get("_ls_loaded"):
        return

    components.html(
        f"""<script>
        (function() {{
            if (window.parent.__dbxSessionsLoaderRan) return;
            window.parent.__dbxSessionsLoaderRan = true;

            const activeSessionId = window.parent.localStorage.getItem("{SESSION_STORAGE_KEY}") || "";
            const sessionsStored = window.parent.localStorage.getItem("{SESSIONS_STORAGE_KEY}");
            let payload = null;

            const buildTitle = (messages) => {{
                const firstUser = (messages || []).find((message) => {{
                    const text = ((message && (message.raw_content || message.content)) || "").trim();
                    return message && message.role === "user" && text;
                }});
                const text = firstUser ? (firstUser.raw_content || firstUser.content || "").replace(/\\s+/g, " ").trim() : "";
                if (!text) return "New chat";
                return text.length > 40 ? `${{text.slice(0, 40)}}...` : text;
            }};

            if (sessionsStored) {{
                try {{
                    const sessions = JSON.parse(sessionsStored);
                    if (Array.isArray(sessions)) {{
                        payload = JSON.stringify({{ active_session_id: activeSessionId, sessions }});
                    }}
                }} catch(e) {{
                    payload = null;
                }}
            }}

            if (!payload) {{
                const storedMessages = window.parent.localStorage.getItem("{STORAGE_KEY}");
                if (!storedMessages) return;

                try {{
                    const messages = JSON.parse(storedMessages);
                    if (!Array.isArray(messages) || !messages.length) return;

                    const fallbackSessionId = activeSessionId || "legacy-session";
                    const now = new Date().toISOString();
                    payload = JSON.stringify({{
                        active_session_id: fallbackSessionId,
                        sessions: [{{
                            id: fallbackSessionId,
                            title: buildTitle(messages),
                            messages: messages,
                            created_at: now,
                            updated_at: now
                        }}]
                    }});
                }} catch(e) {{
                    return;
                }}
            }}

            const bridge = window.parent.document.querySelector('textarea[aria-label="{SESSIONS_BRIDGE_KEY}"]');
            if (!bridge) return;

            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                window.parent.HTMLTextAreaElement.prototype,
                'value'
            ).set;
            nativeInputValueSetter.call(bridge, payload);
            bridge.dispatchEvent(new Event('input', {{ bubbles: true }}));
            bridge.dispatchEvent(new Event('change', {{ bubbles: true }}));
        }})();
        </script>""",
        height=1,
    )


def render_history_bridge():
    """Render hidden bridge textareas that JS writes localStorage data into."""
    st.markdown(
        '<div style="position:absolute;left:-9999px;height:1px;overflow:hidden;">',
        unsafe_allow_html=True,
    )
    st.text_area(
        BRIDGE_KEY,
        key=BRIDGE_KEY,
        value="",
        label_visibility="collapsed",
        height=1,
    )
    st.text_area(
        SESSIONS_BRIDGE_KEY,
        key=SESSIONS_BRIDGE_KEY,
        value="",
        label_visibility="collapsed",
        height=1,
    )
    st.markdown('</div>', unsafe_allow_html=True)


def try_restore_from_local_storage() -> list:
    """Check if the bridge has saved sessions and restore the active session."""
    sessions_bridge_value = st.session_state.get(SESSIONS_BRIDGE_KEY, "")
    if sessions_bridge_value and sessions_bridge_value.strip():
        try:
            payload = json.loads(sessions_bridge_value)
            if isinstance(payload, dict):
                raw_sessions = payload.get("sessions", [])
                active_session_id = payload.get("active_session_id", "")
            elif isinstance(payload, list):
                raw_sessions = payload
                active_session_id = ""
            else:
                raw_sessions = []
                active_session_id = ""

            normalized_sessions = []
            seen_ids = set()
            for session in raw_sessions:
                normalized_session = _normalize_session_record(session)
                if not normalized_session or normalized_session["id"] in seen_ids:
                    continue
                seen_ids.add(normalized_session["id"])
                normalized_sessions.append(normalized_session)

            normalized_sessions = _sort_sessions(normalized_sessions)[:MAX_CHAT_SESSIONS]
            if normalized_sessions:
                selected_session = next(
                    (session for session in normalized_sessions if session["id"] == active_session_id),
                    normalized_sessions[0],
                )
                st.session_state["chat_sessions"] = normalized_sessions
                st.session_state["session_id"] = selected_session["id"]
                st.session_state[BRIDGE_KEY] = ""
                st.session_state[SESSIONS_BRIDGE_KEY] = ""
                st.session_state["_ls_loaded"] = True
                return selected_session.get("messages", [])
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    bridge_value = st.session_state.get(BRIDGE_KEY, "")
    if not bridge_value or bridge_value.strip() == "":
        return []

    try:
        messages = json.loads(bridge_value)
        if isinstance(messages, list) and messages:
            session_id = st.session_state.get("session_id") or str(uuid.uuid4())
            timestamp = _utc_now_iso()
            st.session_state["chat_sessions"] = [
                {
                    "id": session_id,
                    "title": build_chat_session_title(messages),
                    "messages": _slim_messages(messages),
                    "created_at": timestamp,
                    "updated_at": timestamp,
                }
            ]
            st.session_state[BRIDGE_KEY] = ""
            st.session_state["_ls_loaded"] = True
            return messages
    except (json.JSONDecodeError, TypeError):
        pass

    return []


def get_chat_sessions_for_sidebar(limit: int = MAX_SIDEBAR_SESSIONS) -> list:
    sessions = list(_ensure_chat_sessions_state())
    current_session_id = st.session_state.get("session_id", "")
    current_messages = st.session_state.get("messages", [])

    if current_session_id and not any(session["id"] == current_session_id for session in sessions):
        timestamp = _utc_now_iso()
        sessions.append(
            {
                "id": current_session_id,
                "title": build_chat_session_title(current_messages),
                "messages": _slim_messages(current_messages),
                "created_at": timestamp,
                "updated_at": timestamp,
            }
        )

    sessions = _sort_sessions(sessions)
    current_session = next((session for session in sessions if session["id"] == current_session_id), None)
    other_sessions = [session for session in sessions if session["id"] != current_session_id]
    ordered_sessions = ([] if current_session is None else [current_session]) + other_sessions
    return ordered_sessions[:limit]


def format_chat_session_label(session: dict) -> str:
    title = (session or {}).get("title") or "New chat"
    updated_at = (session or {}).get("updated_at") or ""

    if updated_at:
        try:
            timestamp = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            date_label = timestamp.astimezone().strftime("%b %d, %Y %I:%M %p")
            return f"{title} ? {date_label}"
        except ValueError:
            pass

    return title


def start_new_chat():
    current_session_id = st.session_state.get("session_id", "")
    if current_session_id:
        save_chat_to_local_storage(st.session_state.get("messages", []), current_session_id)

    new_session_id = str(uuid.uuid4())
    st.session_state["session_id"] = new_session_id
    st.session_state["messages"] = []
    st.session_state["show_feedback_details"] = False
    st.session_state["_ls_loaded"] = True
    st.session_state["chat_session_selector"] = new_session_id
    save_chat_to_local_storage([], new_session_id)


def switch_chat_session(target_session_id: str) -> bool:
    if not target_session_id or target_session_id == st.session_state.get("session_id"):
        return False

    current_session_id = st.session_state.get("session_id", "")
    if current_session_id:
        save_chat_to_local_storage(st.session_state.get("messages", []), current_session_id)

    sessions = _ensure_chat_sessions_state()
    target_session = next((session for session in sessions if session["id"] == target_session_id), None)
    if not target_session:
        return False

    st.session_state["session_id"] = target_session["id"]
    st.session_state["messages"] = target_session.get("messages", [])
    st.session_state["show_feedback_details"] = False
    st.session_state["_ls_loaded"] = True
    st.session_state["chat_session_selector"] = target_session["id"]
    save_chat_to_local_storage(st.session_state["messages"], target_session["id"])
    return True


def clear_current_chat():
    current_session_id = st.session_state.get("session_id", "")
    sessions = [session for session in _ensure_chat_sessions_state() if session["id"] != current_session_id]
    st.session_state["chat_sessions"] = sessions

    new_session_id = str(uuid.uuid4())
    st.session_state["session_id"] = new_session_id
    st.session_state["messages"] = []
    st.session_state["show_feedback_details"] = False
    st.session_state["_ls_loaded"] = True
    st.session_state["chat_session_selector"] = new_session_id
    save_chat_to_local_storage([], new_session_id)


def clear_local_storage():
    """Render a component that clears all chat history from localStorage."""
    st.session_state["chat_sessions"] = []
    components.html(
        f"""<script>
        window.parent.localStorage.removeItem("{SESSIONS_STORAGE_KEY}");
        window.parent.localStorage.removeItem("{STORAGE_KEY}");
        window.parent.localStorage.removeItem("{SESSION_STORAGE_KEY}");
        window.parent.__dbxHistoryLoaderRan = false;
        window.parent.__dbxSessionsLoaderRan = false;
        </script>""",
        height=1,
    )
