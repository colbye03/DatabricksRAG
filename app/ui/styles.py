APP_BUILD_MARKER = "shareable-report-download-2026-05-06-01"

APP_CSS = """
    :root {
        --dbx-ink: #0b1220;
        --dbx-panel: #ffffff;
        --dbx-muted: #5b677a;
        --dbx-line: #d7dde8;
        --dbx-blue: #2563eb;
        --dbx-cyan: #0891b2;
        --dbx-green: #16a34a;
        --dbx-amber: #d97706;
    }
    .stApp {
        background:
            linear-gradient(180deg, #f7f9fc 0%, #eef3f8 52%, #f8fafc 100%);
    }
    .block-container {
        padding-top: 1.05rem;
        padding-bottom: 3rem;
        max-width: 1460px;
    }
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #ffffff 0%, #f5f8fb 100%);
        border-right: 1px solid rgba(15, 23, 42, 0.08);
    }
    div[data-testid="stVerticalBlock"] > div:has(.dbx-command-hero) {
        margin-bottom: 0.25rem;
    }
    .dbx-command-hero {
        position: sticky;
        top: 0.45rem;
        z-index: 6;
        overflow: hidden;
        border: 1px solid rgba(148, 163, 184, 0.32);
        border-radius: 8px;
        background:
            linear-gradient(135deg, rgba(11, 18, 32, 0.98) 0%, rgba(17, 34, 64, 0.98) 54%, rgba(12, 74, 110, 0.98) 100%);
        color: #f8fafc;
        padding: 0.72rem 0.85rem;
        box-shadow: 0 12px 28px rgba(15, 23, 42, 0.18);
    }
    .dbx-command-hero::before {
        content: "";
        position: absolute;
        inset: 0;
        background-image:
            linear-gradient(rgba(255,255,255,0.035) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255,255,255,0.035) 1px, transparent 1px);
        background-size: 28px 28px;
        pointer-events: none;
    }
    .dbx-command-hero::after {
        content: "";
        position: absolute;
        left: 0;
        right: 0;
        bottom: 0;
        height: 4px;
        background: linear-gradient(90deg, #ff5f46 0%, #2563eb 38%, #0891b2 68%, #16a34a 100%);
    }
    .dbx-command-inner {
        position: relative;
        z-index: 1;
        max-width: 980px;
    }
    .dbx-kicker {
        color: #9bd7ff;
        font-size: 0.72rem;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0;
        margin-bottom: 0.12rem;
    }
    .dbx-command-title {
        font-size: 1.52rem;
        line-height: 1.78rem;
        font-weight: 850;
        letter-spacing: 0;
        margin: 0;
    }
    .dbx-command-copy {
        margin-top: 0.28rem;
        max-width: 900px;
        color: #d9e5f2;
        font-size: 0.84rem;
        line-height: 1.14rem;
    }
    .evidence-strip {
        border: 1px solid rgba(148, 163, 184, 0.28);
        border-radius: 8px;
        background: rgba(255, 255, 255, 0.72);
        color: #334155;
        padding: 0.55rem 0.7rem;
        margin: 0.35rem 0 0.65rem 0;
        font-size: 0.84rem;
        line-height: 1.24rem;
    }
    .evidence-strip strong { color: #0f172a; }
    .evidence-strip.thin {
        border-color: #fbbf24;
        background: #fffbeb;
    }
    .evidence-strip.strong {
        border-color: #86efac;
        background: #f0fdf4;
    }
    .stChatMessage {
        border: 1px solid rgba(148, 163, 184, 0.24);
        border-radius: 8px;
        background: rgba(255, 255, 255, 0.78);
        box-shadow: 0 8px 18px rgba(15, 23, 42, 0.06);
    }
    div[data-testid="stExpander"] {
        border-radius: 8px;
        border-color: rgba(148, 163, 184, 0.32);
        background: rgba(255, 255, 255, 0.72);
    }
    div[data-testid="stChatInput"] {
        border-radius: 8px;
        box-shadow: 0 14px 30px rgba(15, 23, 42, 0.14);
    }
    button[kind="primary"], button[kind="secondary"], .stButton > button {
        border-radius: 8px !important;
        font-weight: 760 !important;
    }
    @media (max-width: 980px) {
        .dbx-command-title { font-size: 1.38rem; line-height: 1.66rem; }
    }
    section[data-testid="stSidebar"] .source-card {
        border: 1px solid #d1d5db;
        border-radius: 0.65rem;
        padding: 0.65rem;
        margin: 0.45rem 0;
        background: #ffffff;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    }
    section[data-testid="stSidebar"] .source-title {
        font-weight: 700;
        color: #111827;
        font-size: 0.9rem;
        line-height: 1.25rem;
    }
    section[data-testid="stSidebar"] .source-meta {
        color: #6b7280;
        font-size: 0.78rem;
        margin-top: 0.15rem;
    }
    .quality-badge {
        display: inline-block;
        padding: 0.15rem 0.45rem;
        border-radius: 999px;
        background: #eef2ff;
        color: #3730a3;
        font-size: 0.78rem;
        font-weight: 700;
    }
    .dbx-status-banner {
        border: 1px solid #bbf7d0;
        border-left: 5px solid #16a34a;
        border-radius: 0.5rem;
        background: #f0fdf4;
        color: #14532d;
        padding: 0.75rem 0.9rem;
        margin-top: 0.35rem;
        margin-bottom: 0.9rem;
    }
    section[data-testid="stSidebar"] .dbx-status-banner {
        border-left-width: 4px;
        padding: 0.62rem 0.68rem;
        margin: 0.15rem 0 0.75rem 0;
    }
    section[data-testid="stSidebar"] .dbx-status-heading {
        align-items: flex-start;
        gap: 0.45rem;
        font-size: 0.86rem;
        line-height: 1.14rem;
    }
    section[data-testid="stSidebar"] .dbx-status-subtext {
        font-size: 0.75rem;
        line-height: 1.1rem;
    }
    section[data-testid="stSidebar"] .dbx-status-pill {
        padding: 0.12rem 0.42rem;
        font-size: 0.68rem;
    }
    section[data-testid="stSidebar"] .dbx-status-issue-list {
        margin-top: 0.5rem;
    }
    section[data-testid="stSidebar"] .dbx-status-issue-row {
        display: block;
        padding: 0.36rem 0.46rem;
        font-size: 0.76rem;
    }
    section[data-testid="stSidebar"] .dbx-status-issue-state {
        display: block;
        margin-top: 0.08rem;
        text-align: left;
    }
    .dbx-status-banner.issue {
        border-color: #fecaca;
        border-left-color: #dc2626;
        background: #fef2f2;
        color: #7f1d1d;
    }
    .dbx-status-banner.neutral {
        border-color: #bfdbfe;
        border-left-color: #2563eb;
        background: #eff6ff;
        color: #1e3a8a;
    }
    .dbx-status-heading {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.75rem;
        font-weight: 800;
        line-height: 1.25rem;
    }
    .dbx-status-subtext {
        margin-top: 0.25rem;
        font-size: 0.86rem;
        color: inherit;
        opacity: 0.9;
    }
    .dbx-status-pill {
        flex: 0 0 auto;
        border-radius: 999px;
        background: rgba(22, 163, 74, 0.12);
        color: #166534;
        padding: 0.18rem 0.55rem;
        font-size: 0.76rem;
        font-weight: 800;
    }
    .dbx-status-banner.issue .dbx-status-pill {
        background: rgba(220, 38, 38, 0.12);
        color: #991b1b;
    }
    .dbx-status-banner.neutral .dbx-status-pill {
        background: rgba(37, 99, 235, 0.12);
        color: #1d4ed8;
    }
    .dbx-status-issue-list {
        margin-top: 0.65rem;
        display: grid;
        gap: 0.35rem;
    }
    .dbx-status-issue-row {
        display: flex;
        justify-content: space-between;
        gap: 0.75rem;
        border-radius: 0.4rem;
        background: rgba(255, 255, 255, 0.72);
        padding: 0.42rem 0.55rem;
        font-size: 0.86rem;
    }
    .dbx-status-issue-name { font-weight: 800; }
    .dbx-status-issue-state {
        color: #b91c1c;
        font-weight: 800;
        text-align: right;
    }
    section[data-testid="stSidebar"] .route-callout {
        border: 1px solid #93c5fd;
        border-left: 4px solid #2563eb;
        border-radius: 0.5rem;
        background: #eff6ff;
        padding: 0.7rem 0.75rem;
        margin: 0.7rem 0 0.45rem 0;
    }
    section[data-testid="stSidebar"] .route-callout-title {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.55rem;
        color: #1e3a8a;
        font-size: 0.86rem;
        line-height: 1.15rem;
        font-weight: 800;
    }
    section[data-testid="stSidebar"] .route-callout-pill {
        flex: 0 0 auto;
        border-radius: 999px;
        background: rgba(37, 99, 235, 0.12);
        color: #1d4ed8;
        padding: 0.12rem 0.44rem;
        font-size: 0.68rem;
        font-weight: 800;
    }
    section[data-testid="stSidebar"] .route-callout-text {
        color: #1e40af;
        margin-top: 0.28rem;
        font-size: 0.76rem;
        line-height: 1.1rem;
    }
    section[data-testid="stSidebar"] .route-callout.route-callout-inner {
        border: 0;
        border-left: 0;
        background: transparent;
        padding: 0;
        margin: 0 0 0.55rem 0;
    }
    section[data-testid="stSidebar"] div[data-testid="stSelectbox"]:has(label[for*="Product route"]) {
        border: 1px solid #bfdbfe;
        border-radius: 0.5rem;
        background: #ffffff;
        padding: 0.45rem 0.55rem 0.35rem 0.55rem;
        box-shadow: 0 1px 3px rgba(37, 99, 235, 0.12);
    }
"""
