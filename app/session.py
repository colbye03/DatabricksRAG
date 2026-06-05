import inspect
import re
import uuid

import streamlit as st
import streamlit.components.v1 as components

from app.config import MAX_HISTORY_CHARS_PER_MESSAGE, MAX_HISTORY_MESSAGES, REASONING_MODEL

EXAMPLE_PLACEHOLDER = "Choose an example question..."


def parse_example_question_selection(selection: str):
    match = re.match(r"^(?P<route>.+?) route, (?P<mode>.+?) mode:\s*(?P<question>.+)$", selection or "")
    if not match:
        return None, None, selection

    route = match.group("route").strip()
    mode = match.group("mode").strip()
    question = match.group("question").strip()

    route_map = {
        "Databricks": "Databricks",
        "Fabric / Power BI": "Fabric / Power BI",
        "Compare / Better Together": "Compare / Better Together",
    }
    mode_map = {
        "Customer Meeting Prep": "Customer Meeting Prep",
        "Solution Architecture": "Solution Architecture",
        "Troubleshooting": "Troubleshooting",
        "Learning": "Learning",
        "Deep Explanation": "Deep Explanation",
        "Implementation / Step-by-step": "Implementation / Step-by-step",
        "Competitive / Customer Positioning": "Competitive / Customer Positioning",
    }

    return route_map.get(route), mode_map.get(mode), question


def queue_selected_example_question():
    selected = st.session_state.get("example_question_picker", "")

    if selected and selected != EXAMPLE_PLACEHOLDER:
        route_label, mode_label, prompt = parse_example_question_selection(selected)

        if route_label:
            st.session_state["product_route_label"] = route_label
        if mode_label:
            st.session_state["answer_mode_label"] = mode_label

        st.session_state["pending_example_prompt"] = prompt
        st.session_state["last_example_selection"] = selected
        st.session_state["example_question_picker"] = EXAMPLE_PLACEHOLDER


def queue_answer_mode_regeneration():
    if st.session_state.get("last_answer"):
        st.session_state["pending_answer_mode_regeneration"] = True


def queue_reasoning_model_regeneration():
    if st.session_state.get("last_answer"):
        st.session_state["pending_answer_mode_regeneration"] = True


def queue_product_route_regeneration():
    if st.session_state.get("last_answer"):
        st.session_state["pending_answer_mode_regeneration"] = True


def init_chat_state():
    if "session_id" not in st.session_state:
        st.session_state["session_id"] = str(uuid.uuid4())

    if "messages" not in st.session_state:
        st.session_state["messages"] = []

    if "show_feedback_details" not in st.session_state:
        st.session_state["show_feedback_details"] = False

    if "last_sources" not in st.session_state:
        st.session_state["last_sources"] = []

    if "last_example_selection" not in st.session_state:
        st.session_state["last_example_selection"] = ""

    if "pending_example_prompt" not in st.session_state:
        st.session_state["pending_example_prompt"] = ""

    if "example_question_picker" not in st.session_state:
        st.session_state["example_question_picker"] = EXAMPLE_PLACEHOLDER

    if "pending_answer_mode_regeneration" not in st.session_state:
        st.session_state["pending_answer_mode_regeneration"] = False

    if "reasoning_model_endpoint" not in st.session_state:
        st.session_state["reasoning_model_endpoint"] = REASONING_MODEL



def truncate_text(text: str, max_chars: int) -> str:
    text = text or ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...[truncated]"


def get_recent_chat_history_before_current(max_messages: int = MAX_HISTORY_MESSAGES) -> str:
    messages = st.session_state.get("messages", [])
    history_messages = messages[:-1][-max_messages:]

    lines = []
    for msg in history_messages:
        role = msg.get("role", "user").upper()
        content = msg.get("raw_content") or msg.get("content", "")
        content = truncate_text(content, MAX_HISTORY_CHARS_PER_MESSAGE)
        lines.append(f"{role}: {content}")

    return "\n\n".join(lines)


def normalize_chat_input(chat_value):
    if chat_value is None:
        return "", []

    if isinstance(chat_value, str):
        return chat_value, []

    text = ""
    files = []

    try:
        text = getattr(chat_value, "text", "") or ""
    except Exception:
        text = ""

    try:
        files = getattr(chat_value, "files", []) or []
    except Exception:
        files = []

    if isinstance(chat_value, dict):
        text = chat_value.get("text", text) or ""
        files = chat_value.get("files", files) or []

    if files is None:
        files = []

    if not isinstance(files, list):
        files = [files]

    return text, files


def chat_input_supports_files() -> bool:
    try:
        sig = inspect.signature(st.chat_input)
        return "accept_file" in sig.parameters
    except Exception:
        return False


CHAT_INPUT_FILE_SUPPORT = chat_input_supports_files()
sidebar_uploaded_file = None


def render_paste_screenshot_helper():
    """Enable Ctrl+V screenshot paste into the nearest Streamlit file input when the browser allows it."""
    components.html(
        """
        <script>
        (function () {
            const doc = window.parent.document;
            if (window.parent.__dbxPasteScreenshotHelperInstalled) return;
            window.parent.__dbxPasteScreenshotHelperInstalled = true;

                    function findFileInput() {
                        const inputs = Array.from(doc.querySelectorAll('input[type="file"]'));
                        return inputs.find((input) => {
                            const accept = (input.getAttribute('accept') || '').toLowerCase();
                            return accept.includes('png') || accept.includes('jpg') || accept.includes('jpeg') || accept.includes('image');
                        }) || inputs[inputs.length - 1];
                    }

                    function showPasteToast(message, isError) {
                        let toast = doc.getElementById('dbx-paste-screenshot-toast');
                        if (!toast) {
                            toast = doc.createElement('div');
                            toast.id = 'dbx-paste-screenshot-toast';
                            toast.style.position = 'fixed';
                            toast.style.right = '24px';
                            toast.style.bottom = '88px';
                            toast.style.zIndex = '999999';
                            toast.style.padding = '10px 14px';
                            toast.style.borderRadius = '10px';
                            toast.style.boxShadow = '0 6px 18px rgba(0,0,0,.22)';
                            toast.style.fontFamily = 'system-ui, -apple-system, Segoe UI, sans-serif';
                            toast.style.fontSize = '13px';
                            doc.body.appendChild(toast);
                        }
                        toast.textContent = message;
                        toast.style.background = isError ? '#7f1d1d' : '#064e3b';
                        toast.style.color = '#ffffff';
                        toast.style.display = 'block';
                        clearTimeout(window.parent.__dbxPasteScreenshotToastTimer);
                        window.parent.__dbxPasteScreenshotToastTimer = setTimeout(() => { toast.style.display = 'none'; }, 3500);
                    }

                    doc.addEventListener('paste', function (event) {
                        const clipboard = event.clipboardData;
                        const items = clipboard && clipboard.items ? Array.from(clipboard.items) : [];
                        const imageItems = items.filter((item) => item.type && item.type.startsWith('image/'));
                        if (!imageItems.length) return;

                        const hasTextPayload = Boolean(
                            (clipboard && clipboard.getData && clipboard.getData('text/plain')) ||
                            (clipboard && clipboard.getData && clipboard.getData('text/html')) ||
                            items.some((item) => item.kind === 'string' && item.type && item.type.startsWith('text/'))
                        );
                        if (hasTextPayload) return;

                        const input = findFileInput();
                        if (!input) {
                            showPasteToast('Screenshot found, but no upload control is available yet.', true);
                            return;
                        }

                        const dataTransfer = new DataTransfer();
                        Array.from(input.files || []).forEach((file) => dataTransfer.items.add(file));

                        imageItems.forEach((imageItem, index) => {
                            const blob = imageItem.getAsFile();
                            if (!blob) return;

                            const extension = (blob.type || 'image/png').includes('jpeg') ? 'jpg' : 'png';
                            const file = new File(
                                [blob],
                                `pasted-screenshot-${Date.now()}-${index + 1}.${extension}`,
                                { type: blob.type || 'image/png' }
                            );
                            dataTransfer.items.add(file);
                        });

                        if (!dataTransfer.files.length) return;

                        input.files = dataTransfer.files;
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                        input.dispatchEvent(new Event('input', { bubbles: true }));

                        const addedCount = imageItems.length;
                        const totalCount = dataTransfer.files.length;
                        const addedLabel = addedCount === 1 ? 'screenshot' : 'screenshots';
                        showPasteToast(`${addedCount} ${addedLabel} pasted. ${totalCount} total attachment${totalCount === 1 ? '' : 's'} ready.`, false);
                    }, true);
                })();
                </script>
            """,
            height=0,
            )


def render_scroll_to_latest_exchange_script():
    components.html(
        """
        <script>
        (function () {
            const doc = window.parent.document;
            const anchor = doc.getElementById('dbx-latest-exchange-start');
            if (!anchor) return;

            setTimeout(() => {
                anchor.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }, 120);
        })();
        </script>
        """,
        height=0,
    )
