import html
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
import streamlit as st


APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DATABASE_PATH = DATA_DIR / "securerepo.db"


st.set_page_config(
    page_title="SecureRepo AI",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)


def load_styles():
    style_path = APP_DIR / "styles.css"

    if style_path.exists():
        css = style_path.read_text(encoding="utf-8")
        st.markdown(
            f"<style>{css}</style>",
            unsafe_allow_html=True,
        )


load_styles()


def get_setting(name):
    environment_value = os.getenv(name, "").strip()

    if environment_value:
        return environment_value

    try:
        return str(st.secrets.get(name, "")).strip()
    except (FileNotFoundError, KeyError):
        return ""


BACKEND_URL = get_setting(
    "SECUREREPO_BACKEND_URL"
).rstrip("/")

API_KEY = get_setting(
    "SECUREREPO_API_KEY"
)


def initialize_database():
    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS scans (
                scan_id TEXT PRIMARY KEY,
                user_email TEXT NOT NULL,
                repository TEXT NOT NULL,
                repository_name TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                risk_score INTEGER NOT NULL,
                total_findings INTEGER NOT NULL,
                critical_count INTEGER NOT NULL,
                high_count INTEGER NOT NULL,
                medium_count INTEGER NOT NULL,
                low_count INTEGER NOT NULL,
                report_json TEXT NOT NULL
            )
            """
        )

        connection.commit()


def calculate_report_risk(report):
    file_scores = []

    for file_result in report.get(
        "analysis",
        [],
    ):
        review = file_result.get(
            "review",
            {},
        )

        try:
            file_scores.append(
                int(review.get("risk_score", 0))
            )
        except (TypeError, ValueError):
            continue

    if file_scores:
        return max(
            0,
            min(100, max(file_scores)),
        )

    severity_counts = report.get(
        "severity_counts",
        {},
    )

    if severity_counts.get("critical", 0):
        return 95

    if severity_counts.get("high", 0):
        return 80

    if severity_counts.get("medium", 0):
        return 60

    if severity_counts.get("low", 0):
        return 30

    return 0


def repository_name(repository_url):
    path = urlparse(
        repository_url
    ).path.strip("/")

    name = path.split("/")[-1] if path else "repository"

    if name.endswith(".git"):
        name = name[:-4]

    return name or "repository"


def save_report(report, user_email):
    severity_counts = report.get(
        "severity_counts",
        {},
    )

    risk_score = calculate_report_risk(
        report
    )

    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO scans (
                scan_id,
                user_email,
                repository,
                repository_name,
                completed_at,
                risk_score,
                total_findings,
                critical_count,
                high_count,
                medium_count,
                low_count,
                report_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report.get("scan_id", ""),
                user_email,
                report.get("repository", ""),
                repository_name(
                    report.get("repository", "")
                ),
                report.get(
                    "completed_at",
                    datetime.now().isoformat(),
                ),
                risk_score,
                int(
                    report.get(
                        "total_confirmed_findings",
                        0,
                    )
                ),
                int(
                    severity_counts.get(
                        "critical",
                        0,
                    )
                ),
                int(
                    severity_counts.get(
                        "high",
                        0,
                    )
                ),
                int(
                    severity_counts.get(
                        "medium",
                        0,
                    )
                ),
                int(
                    severity_counts.get(
                        "low",
                        0,
                    )
                ),
                json.dumps(
                    report,
                    ensure_ascii=False,
                ),
            ),
        )

        connection.commit()


def get_scan_history(
    user_email,
    limit=100,
):
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.row_factory = sqlite3.Row

        rows = connection.execute(
            """
            SELECT
                scan_id,
                repository,
                repository_name,
                completed_at,
                risk_score,
                total_findings,
                critical_count,
                high_count,
                medium_count,
                low_count
            FROM scans
            WHERE user_email = ?
            ORDER BY completed_at DESC
            LIMIT ?
            """,
            (
                user_email,
                limit,
            ),
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]


def get_saved_report(
    scan_id,
    user_email,
):
    with sqlite3.connect(DATABASE_PATH) as connection:
        row = connection.execute(
            """
            SELECT report_json
            FROM scans
            WHERE scan_id = ?
              AND user_email = ?
            """,
            (
                scan_id,
                user_email,
            ),
        ).fetchone()

    if row is None:
        return None

    return json.loads(
        row[0]
    )


initialize_database()


def initialize_session():
    defaults = {
        "authenticated": False,
        "user_email": "",
        "navigation": "Overview",
        "current_report": None,
        "selected_report_id": None,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


initialize_session()


@st.cache_data(
    ttl=8,
    show_spinner=False,
)
def check_backend(backend_url):
    if not backend_url:
        return {
            "online": False,
            "message": "Backend URL is not configured.",
        }

    try:
        response = requests.get(
            f"{backend_url}/health",
            headers={
                "ngrok-skip-browser-warning": "true",
            },
            timeout=6,
        )

        response.raise_for_status()
        health = response.json()

        reviewer_ready = bool(
            health.get(
                "reviewer_ready",
                (
                    health.get(
                        "gpu_available",
                        False,
                    )
                    and health.get(
                        "model_loaded",
                        False,
                    )
                ),
            )
        )

        return {
            **health,
            "online": True,
            "ready": reviewer_ready,
        }

    except Exception as error:
        return {
            "online": False,
            "message": str(error),
        }


def safe_text(value):
    return html.escape(
        (
            ""
            if value is None
            else str(value)
        ),
        quote=True,
    )


def format_time(value):
    if not value:
        return "Unknown time"

    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

        return parsed.astimezone().strftime(
            "%d %b %Y · %I:%M %p"
        )

    except (TypeError, ValueError):
        return str(value)


def risk_class(score):
    if score >= 90:
        return "critical"

    if score >= 70:
        return "high"

    if score >= 40:
        return "medium"

    if score > 0:
        return "low"

    return "safe"


def risk_label(score):
    labels = {
        "critical": "Critical",
        "high": "High risk",
        "medium": "Medium risk",
        "low": "Low risk",
        "safe": "No findings",
    }

    return labels[
        risk_class(score)
    ]


def page_heading(
    eyebrow,
    title,
    description,
):
    st.markdown(
        f"""
        <div class="sr-page-heading">
            <div class="sr-eyebrow">
                {safe_text(eyebrow)}
            </div>
            <h1>{safe_text(title)}</h1>
            <p>{safe_text(description)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def metric_card(
    label,
    value,
    detail,
    accent="cyan",
):
    allowed_accents = {
        "cyan",
        "violet",
        "red",
        "orange",
        "muted",
    }

    if accent not in allowed_accents:
        accent = "cyan"

    card_html = (
        f'<div class="sr-metric sr-accent-{accent}">'
        f'<div class="sr-metric-label">{safe_text(label)}</div>'
        f'<div class="sr-metric-value">{safe_text(value)}</div>'
        f'<div class="sr-metric-detail">{safe_text(detail)}</div>'
        "</div>"
    )

    st.markdown(
        card_html,
        unsafe_allow_html=True,
    )


def severity_badge(severity):
    normalized = str(
        severity or "medium"
    ).lower()

    if normalized not in {
        "critical",
        "high",
        "medium",
        "low",
    }:
        normalized = "medium"

    return normalized


def extract_findings(report):
    findings = []

    for file_result in report.get(
        "analysis",
        [],
    ):
        review = file_result.get(
            "review",
            {},
        )

        findings.extend(
            review.get(
                "findings",
                [],
            )
        )

    return findings


def get_skipped_file_details(report):
    skipped_files = report.get(
        "files_skipped",
        [],
    ) or []

    file_errors = report.get(
        "file_errors",
        {},
    ) or {}

    details = []

    for skipped in skipped_files:
        if isinstance(skipped, dict):
            file_name = str(
                skipped.get(
                    "file",
                    "Unknown file",
                )
            )

            message = str(
                skipped.get(
                    "message",
                    file_errors.get(
                        file_name,
                        "Analysis failed.",
                    ),
                )
            )
        else:
            file_name = str(skipped)
            message = str(
                file_errors.get(
                    file_name,
                    "Analysis failed.",
                )
            )

        details.append(
            (
                file_name,
                message,
            )
        )

    return details


def render_skipped_files(
    skipped_details,
    expanded=False,
):
    if not skipped_details:
        return

    with st.expander(
        "Skipped files and errors",
        expanded=expanded,
    ):
        for file_name, message in skipped_details:
            st.markdown("**File**")
            st.code(
                file_name,
                language=None,
            )
            st.caption(message)


def render_finding(
    finding,
    number,
    expanded=False,
):
    severity = severity_badge(
        finding.get("severity")
    )

    file_name = finding.get(
        "file",
        "Unknown file",
    )

    line_start = finding.get(
        "line_start",
        "?",
    )

    line_end = finding.get(
        "line_end",
        line_start,
    )

    with st.container(border=True):
        st.markdown(
            f"""
            <div class="sr-finding-top">
                <div>
                    <div class="sr-finding-number">
                        FINDING {number:02d}
                    </div>
                    <div class="sr-finding-title">
                        {safe_text(finding.get("title", "Security finding"))}
                    </div>
                    <div class="sr-finding-location">
                        {safe_text(file_name)}
                        · lines {safe_text(line_start)}–{safe_text(line_end)}
                    </div>
                </div>
                <span class="sr-badge sr-{severity}">
                    {severity.upper()}
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        details = (
            f"{finding.get('cwe_id', 'CWE unknown')} · "
            f"{finding.get('owasp_category', 'OWASP category unknown')} · "
            f"{finding.get('scanner_rule', 'Rule unknown')} · "
            f"{str(finding.get('confidence', 'medium')).title()} confidence"
        )

        st.caption(details)

        with st.expander(
            "Evidence, impact and remediation",
            expanded=expanded,
        ):
            evidence_tab, analysis_tab, fix_tab, verification_tab = (
                st.tabs(
                    [
                        "Evidence",
                        "Analysis",
                        "Recommended fix",
                        "Verification",
                    ]
                )
            )

            with evidence_tab:
                st.markdown(
                    "##### Vulnerable code"
                )
                st.code(
                    finding.get(
                        "evidence",
                        "No evidence supplied.",
                    ),
                    language="python",
                )

            with analysis_tab:
                st.markdown(
                    "##### Why this is unsafe"
                )
                st.write(
                    finding.get(
                        "explanation",
                        "No explanation supplied.",
                    )
                )

                st.markdown(
                    "##### Possible impact"
                )
                st.write(
                    finding.get(
                        "impact",
                        "No impact supplied.",
                    )
                )

            with fix_tab:
                st.markdown(
                    "##### Recommendation"
                )
                st.write(
                    finding.get(
                        "recommendation",
                        "No recommendation supplied.",
                    )
                )

                st.markdown(
                    "##### Safer replacement"
                )
                st.code(
                    finding.get(
                        "fixed_code",
                        "No replacement supplied.",
                    ),
                    language="python",
                )

            with verification_tab:
                verification_columns = st.columns(2)

                with verification_columns[0]:
                    st.markdown(
                        "**Security classification**"
                    )
                    st.write(
                        finding.get(
                            "cwe_id",
                            "Unknown CWE",
                        )
                    )
                    st.write(
                        finding.get(
                            "owasp_category",
                            "Unknown OWASP category",
                        )
                    )

                with verification_columns[1]:
                    st.markdown(
                        "**Detection evidence**"
                    )
                    st.write(
                        finding.get(
                            "scanner_rule",
                            "Unknown scanner rule",
                        )
                    )
                    st.write(
                        f"{str(finding.get('confidence', 'medium')).title()} "
                        "confidence"
                    )

                st.info(
                    "Verified using source code, Bandit evidence, "
                    "retrieved security guidance, the fine-tuned model, "
                    "and Pydantic validation."
                )


def render_report(
    report,
    key_prefix,
    show_heading=True,
):
    repository = report.get(
        "repository",
        "Unknown repository",
    )

    severity_counts = report.get(
        "severity_counts",
        {},
    )

    findings = extract_findings(
        report
    )

    risk_score = calculate_report_risk(
        report
    )

    try:
        files_analyzed = int(
            report.get(
                "files_analyzed",
                0,
            )
            or 0
        )
    except (TypeError, ValueError):
        files_analyzed = 0

    skipped_details = (
        get_skipped_file_details(
            report
        )
    )

    incomplete_report = (
        files_analyzed == 0
        and bool(skipped_details)
    )

    partial_without_findings = (
        files_analyzed > 0
        and bool(skipped_details)
        and not findings
    )

    risk_value = (
        "—"
        if (
            incomplete_report
            or partial_without_findings
        )
        else risk_score
    )

    risk_state = (
        "unknown"
        if (
            incomplete_report
            or partial_without_findings
        )
        else risk_class(risk_score)
    )

    risk_caption = (
        (
            "NO DATA"
            if incomplete_report
            else "PARTIAL"
        )
        if incomplete_report
        or partial_without_findings
        else "RISK"
    )

    if show_heading:
        st.markdown(
            """
            <div class="sr-section-label">
                VALIDATED SECURITY REPORT
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        f"""
        <div class="sr-report-hero">
            <div>
                <div class="sr-report-label">
                    REPOSITORY ANALYSIS
                </div>
                <h2>{safe_text(repository_name(repository))}</h2>
                <p>{safe_text(repository)}</p>
            </div>
            <div class="sr-risk-ring sr-risk-{risk_state}">
                <span>{risk_value}</span>
                <small>{risk_caption}</small>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    metric_columns = st.columns(5)

    metric_values = [
        (
            "Files analyzed",
            files_analyzed,
            "AI-validated",
            "cyan",
        ),
        (
            "Confirmed",
            len(findings),
            "Total findings",
            "violet",
        ),
        (
            "Critical",
            severity_counts.get(
                "critical",
                0,
            ),
            "Immediate action",
            "red",
        ),
        (
            "High",
            severity_counts.get(
                "high",
                0,
            ),
            "Priority fixes",
            "orange",
        ),
        (
            "Skipped",
            len(skipped_details),
            "Could not analyze",
            "muted",
        ),
    ]

    for column, metric in zip(
        metric_columns,
        metric_values,
    ):
        with column:
            metric_card(*metric)

    st.markdown(
        "#### Severity overview"
    )

    total_for_bar = max(
        1,
        len(findings),
    )

    severity_segments = []

    for severity in [
        "critical",
        "high",
        "medium",
        "low",
    ]:
        count = int(
            severity_counts.get(
                severity,
                0,
            )
        )

        width = (
            count
            / total_for_bar
            * 100
        )

        if width > 0:
            severity_segments.append(
                f"""
                <div
                    class="sr-segment sr-segment-{severity}"
                    style="width:{width}%"
                    title="{severity.title()}: {count}">
                </div>
                """
            )

    if not severity_segments:
        severity_segments.append(
            """
            <div
                class="sr-segment sr-segment-safe"
                style="width:100%">
            </div>
            """
        )

    st.markdown(
        f"""
        <div class="sr-severity-bar">
            {''.join(severity_segments)}
        </div>
        <div class="sr-severity-legend">
            <span>Critical {severity_counts.get("critical", 0)}</span>
            <span>High {severity_counts.get("high", 0)}</span>
            <span>Medium {severity_counts.get("medium", 0)}</span>
            <span>Low {severity_counts.get("low", 0)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    download_columns = st.columns(
        [3, 1]
    )

    with download_columns[0]:
        st.caption(
            "Completed "
            + format_time(
                report.get(
                    "completed_at"
                )
            )
        )

    with download_columns[1]:
        st.download_button(
            "Download JSON report",
            data=json.dumps(
                report,
                indent=2,
                ensure_ascii=False,
            ),
            file_name=(
                f"{repository_name(repository)}"
                "_securerepo_report.json"
            ),
            mime="application/json",
            key=f"{key_prefix}_download",
            use_container_width=True,
        )

    st.divider()
    st.markdown(
        "### Confirmed vulnerabilities"
    )

    if incomplete_report:
        st.error(
            "This scan is incomplete: no Python files were "
            "successfully analyzed. No security conclusion "
            "can be made from this report."
        )

        render_skipped_files(
            skipped_details,
            expanded=True,
        )
        return

    if skipped_details:
        st.warning(
            f"{len(skipped_details)} file(s) could not be "
            "analyzed, so this report has partial coverage."
        )

        render_skipped_files(
            skipped_details
        )

    if not findings:
        if skipped_details:
            st.info(
                "No supported vulnerabilities were confirmed "
                "in the files that completed analysis. Because "
                "coverage is partial, this is not a clean-repository "
                "conclusion."
            )
        else:
            st.success(
                "No supported vulnerabilities were confirmed "
                "in the analyzed files."
            )
        return

    filter_columns = st.columns(
        [1, 2]
    )

    with filter_columns[0]:
        severity_filter = st.selectbox(
            "Severity",
            [
                "All",
                "Critical",
                "High",
                "Medium",
                "Low",
            ],
            key=f"{key_prefix}_severity",
        )

    with filter_columns[1]:
        search_text = st.text_input(
            "Search findings",
            placeholder=(
                "Search by title, file, CWE or scanner rule"
            ),
            key=f"{key_prefix}_search",
        ).strip().lower()

    filtered_findings = []

    for finding in findings:
        if (
            severity_filter != "All"
            and severity_badge(
                finding.get("severity")
            )
            != severity_filter.lower()
        ):
            continue

        searchable_text = " ".join(
            str(
                finding.get(
                    field,
                    "",
                )
            )
            for field in [
                "title",
                "file",
                "cwe_id",
                "owasp_category",
                "scanner_rule",
            ]
        ).lower()

        if (
            search_text
            and search_text not in searchable_text
        ):
            continue

        filtered_findings.append(
            finding
        )

    st.caption(
        f"Showing {len(filtered_findings)} "
        f"of {len(findings)} findings"
    )

    for number, finding in enumerate(
        filtered_findings,
        start=1,
    ):
        render_finding(
            finding,
            number,
            expanded=False,
        )


def authenticate(email):
    cleaned_email = email.strip().lower()

    st.session_state.authenticated = True
    st.session_state.user_email = (
        cleaned_email
        or "demo@securerepo.ai"
    )

    st.rerun()


def render_login():
    st.markdown(
        """
        <div class="sr-login-brand">
            <div class="sr-shield">S</div>
            <div>
                <strong>SecureRepo AI</strong>
                <span>Evidence-based code security</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    left_column, right_column = st.columns(
        [1.15, 0.85],
        gap="large",
        vertical_alignment="center",
    )

    with left_column:
        st.markdown(
            """
            <div class="sr-login-hero">
                <div class="sr-eyebrow">
                    AI-POWERED REPOSITORY DEFENSE
                </div>
                <h1>
                    Find the security flaw<br>
                    <span>before an attacker does.</span>
                </h1>
                <p>
                    SecureRepo combines static analysis, retrieved
                    security knowledge and a fine-tuned open-source
                    model to deliver evidence-backed fixes in real time.
                </p>
                <div class="sr-login-pipeline">
                    <span>Bandit</span>
                    <i>→</i>
                    <span>FAISS RAG</span>
                    <i>→</i>
                    <span>Fine-tuned LoRA</span>
                    <i>→</i>
                    <span>Pydantic</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with right_column:
        st.markdown(
            """
            <div class="sr-auth-heading">
                <div class="sr-auth-kicker">SECURE WORKSPACE</div>
                <h2>Welcome back</h2>
                <p>Sign in to open your repository dashboard.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        login_tab, register_tab = st.tabs(
            [
                "Login",
                "Create account",
            ]
        )

        with login_tab:
            with st.form(
                "login_form",
                clear_on_submit=False,
            ):
                login_email = st.text_input(
                    "Email address",
                    placeholder="name@company.com",
                )

                login_password = st.text_input(
                    "Password",
                    type="password",
                    placeholder="Enter any demo password",
                )

                login_submitted = st.form_submit_button(
                    "Sign in",
                    type="primary",
                    use_container_width=True,
                )

            if login_submitted:
                if (
                    not login_email.strip()
                    or not login_password
                ):
                    st.error(
                        "Enter an email and password."
                    )
                else:
                    authenticate(
                        login_email
                    )

        with register_tab:
            with st.form(
                "register_form",
                clear_on_submit=False,
            ):
                register_email = st.text_input(
                    "Work email",
                    placeholder="name@company.com",
                )

                register_password = st.text_input(
                    "Create password",
                    type="password",
                    placeholder="Demo only",
                )

                register_confirm = st.text_input(
                    "Confirm password",
                    type="password",
                    placeholder="Repeat the password",
                )

                register_submitted = (
                    st.form_submit_button(
                        "Create demo account",
                        type="primary",
                        use_container_width=True,
                    )
                )

            if register_submitted:
                if (
                    not register_email.strip()
                    or not register_password
                ):
                    st.error(
                        "Complete every field."
                    )
                elif (
                    register_password
                    != register_confirm
                ):
                    st.error(
                        "The passwords do not match."
                    )
                else:
                    authenticate(
                        register_email
                    )

        st.markdown(
            """
            <div class="sr-auth-divider">
                <span>or</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button(
            "Continue with demo account",
            use_container_width=True,
        ):
            authenticate(
                "demo@securerepo.ai"
            )

        st.caption(
            "Competition demo authentication — "
            "no production identity system is connected."
        )


def navigate_to(page_name):
    st.session_state.navigation = page_name


def open_saved_report(scan_id):
    st.session_state.selected_report_id = scan_id
    st.session_state.navigation = "Reports"


def render_sidebar():
    health = check_backend(
        BACKEND_URL
    )

    with st.sidebar:
        st.markdown(
            """
            <div class="sr-sidebar-brand">
                <div class="sr-shield sr-shield-small">S</div>
                <div>
                    <strong>SecureRepo AI</strong>
                    <span>Security Intelligence</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            "<div class='sr-sidebar-label'>WORKSPACE</div>",
            unsafe_allow_html=True,
        )

        st.radio(
            "Navigation",
            [
                "Overview",
                "New Scan",
                "Repositories",
                "Scan History",
                "Reports",
                "Settings",
            ],
            key="navigation",
            label_visibility="collapsed",
        )

        st.markdown(
            "<div class='sr-sidebar-spacer'></div>",
            unsafe_allow_html=True,
        )

        if (
            health.get("online")
            and health.get("ready")
        ):
            backend_status = (
                "<span class='sr-status-dot sr-online'></span>"
                "Kaggle GPU connected"
            )
        elif health.get("online"):
            backend_status = (
                "<span class='sr-status-dot sr-offline'></span>"
                "Kaggle backend starting"
            )
        else:
            backend_status = (
                "<span class='sr-status-dot sr-offline'></span>"
                "Kaggle backend offline"
            )

        st.markdown(
            f"""
            <div class="sr-backend-card">
                <div class="sr-backend-title">
                    BACKEND STATUS
                </div>
                <div class="sr-backend-value">
                    {backend_status}
                </div>
                <div class="sr-backend-detail">
                    {(
                        "Model ready for analysis"
                        if health.get("ready")
                        else "Run Kaggle Blocks 1–9 in order"
                    )}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            f"""
            <div class="sr-user-card">
                <div class="sr-avatar">
                    {safe_text(st.session_state.user_email[:1].upper())}
                </div>
                <div>
                    <strong>{safe_text(st.session_state.user_email)}</strong>
                    <span>Demo workspace</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button(
            "Log out",
            use_container_width=True,
        ):
            st.session_state.clear()
            st.rerun()


def render_scan_card(
    scan,
    button_key,
):
    score = int(
        scan.get(
            "risk_score",
            0,
        )
    )

    badge_class = risk_class(
        score
    )

    with st.container(border=True):
        card_columns = st.columns(
            [4, 1.1, 1.2],
            vertical_alignment="center",
        )

        with card_columns[0]:
            st.markdown(
                f"""
                <div class="sr-repo-row">
                    <div class="sr-repo-icon">&lt;/&gt;</div>
                    <div>
                        <strong>
                            {safe_text(scan.get("repository_name", "Repository"))}
                        </strong>
                        <span>
                            {safe_text(scan.get("repository", ""))}
                        </span>
                        <small>
                            {safe_text(format_time(scan.get("completed_at")))}
                        </small>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with card_columns[1]:
            st.markdown(
                f"""
                <div class="sr-row-stat">
                    <strong>{scan.get("total_findings", 0)}</strong>
                    <span>findings</span>
                </div>
                <span class="sr-badge sr-{badge_class}">
                    {safe_text(risk_label(score))}
                </span>
                """,
                unsafe_allow_html=True,
            )

        with card_columns[2]:
            st.button(
                "Open report",
                key=button_key,
                use_container_width=True,
                on_click=open_saved_report,
                args=(
                    scan["scan_id"],
                ),
            )


def render_overview():
    page_heading(
        "SECURITY OPERATIONS",
        "Repository overview",
        (
            "Monitor repository risk, recent scans and "
            "validated vulnerabilities from one workspace."
        ),
    )

    history = get_scan_history(
        st.session_state.user_email
    )

    unique_repositories = {
        scan["repository"]
        for scan in history
    }

    total_findings = sum(
        scan["total_findings"]
        for scan in history
    )

    urgent_findings = sum(
        scan["critical_count"]
        + scan["high_count"]
        for scan in history
    )

    average_risk = (
        round(
            sum(
                scan["risk_score"]
                for scan in history
            )
            / len(history)
        )
        if history
        else 0
    )

    metric_columns = st.columns(4)

    overview_metrics = [
        (
            "Repositories",
            len(unique_repositories),
            "Unique targets scanned",
            "cyan",
        ),
        (
            "Confirmed findings",
            total_findings,
            "Evidence-backed issues",
            "violet",
        ),
        (
            "Critical + high",
            urgent_findings,
            "Priority remediation",
            "red",
        ),
        (
            "Average risk",
            f"{average_risk}/100",
            "Across completed scans",
            "orange",
        ),
    ]

    for column, metric in zip(
        metric_columns,
        overview_metrics,
    ):
        with column:
            metric_card(*metric)

    action_columns = st.columns(
        [3, 1]
    )

    with action_columns[0]:
        st.markdown(
            """
            <div class="sr-section-label">
                RECENT SECURITY ACTIVITY
            </div>
            <h3>Latest repository scans</h3>
            """,
            unsafe_allow_html=True,
        )

    with action_columns[1]:
        st.button(
            "＋ New repository scan",
            type="primary",
            use_container_width=True,
            on_click=navigate_to,
            args=(
                "New Scan",
            ),
        )

    if not history:
        st.markdown(
            """
            <div class="sr-empty-state">
                <div class="sr-empty-icon">⌁</div>
                <h3>No scans yet</h3>
                <p>
                    Connect the Kaggle backend and analyze your
                    first public Python repository.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    for index, scan in enumerate(
        history[:6],
    ):
        render_scan_card(
            scan,
            button_key=f"overview_report_{index}",
        )


class BackendScanError(Exception):
    pass


def update_live_metrics(
    metric_slot,
    current_file,
    total_files,
    completed_files,
    findings_count,
    candidate_findings,
):
    with metric_slot.container():
        columns = st.columns(4)

        values = [
            (
                "Current file",
                (
                    f"{current_file}/{total_files}"
                    if total_files
                    else "—"
                ),
                "Repository progress",
                "cyan",
            ),
            (
                "Processed",
                completed_files,
                "Completed attempts",
                "violet",
            ),
            (
                "AI findings",
                findings_count,
                "Streamed live",
                "red",
            ),
            (
                "Bandit clues",
                candidate_findings,
                "Awaiting verification",
                "orange",
            ),
        ]

        for column, metric in zip(
            columns,
            values,
        ):
            with column:
                metric_card(*metric)


def run_live_scan(
    repository_url,
    file_limit,
):
    if not BACKEND_URL or not API_KEY:
        st.error(
            "The backend URL or API key is missing. "
            "Complete .streamlit/secrets.toml first."
        )
        return None

    st.markdown(
        """
        <div class="sr-section-label">
            LIVE ANALYSIS STREAM
        </div>
        """,
        unsafe_allow_html=True,
    )

    scan_status = st.status(
        "Initializing secure scan...",
        expanded=True,
    )

    progress_bar = st.progress(
        0,
        text="Preparing repository analysis",
    )

    activity_slot = st.empty()
    metric_slot = st.empty()

    st.markdown(
        "### Live vulnerability feed"
    )
    feed_caption = st.empty()
    finding_feed = st.container()

    current_file = 0
    total_files = 0
    completed_files = 0
    findings_count = 0
    candidate_findings = 0
    final_report = None

    update_live_metrics(
        metric_slot,
        current_file,
        total_files,
        completed_files,
        findings_count,
        candidate_findings,
    )

    stage_labels = {
        "cloning_repository": (
            "Cloning the public GitHub repository"
        ),
        "discovering_python": (
            "Discovering readable Python files"
        ),
        "running_bandit": (
            "Running Bandit static analysis"
        ),
        "building_report": (
            "Building the validated final report"
        ),
    }

    try:
        with requests.post(
            f"{BACKEND_URL}/scan/stream",
            json={
                "repo_url": repository_url,
                "file_limit": file_limit,
            },
            headers={
                "X-API-Key": API_KEY,
                "Accept": "application/x-ndjson",
                "ngrok-skip-browser-warning": "true",
            },
            stream=True,
            timeout=(
                20,
                3600,
            ),
        ) as response:
            if response.status_code != 200:
                try:
                    message = response.json().get(
                        "detail",
                        response.text,
                    )
                except ValueError:
                    message = response.text

                raise BackendScanError(
                    f"Backend returned "
                    f"{response.status_code}: {message}"
                )

            for raw_line in response.iter_lines(
                chunk_size=1,
                decode_unicode=True,
            ):
                if not raw_line:
                    continue

                try:
                    event = json.loads(
                        raw_line
                    )
                except json.JSONDecodeError as error:
                    raise BackendScanError(
                        "The backend returned invalid streaming "
                        "data. Restart the final Kaggle block and "
                        "try again."
                    ) from error

                event_type = event.get(
                    "type"
                )

                if event_type == "scan_started":
                    scan_status.write(
                        "Secure scan session created."
                    )

                elif event_type == "stage":
                    stage = event.get(
                        "stage",
                        "",
                    )

                    label = stage_labels.get(
                        stage,
                        event.get(
                            "message",
                            "Processing repository",
                        ),
                    )

                    scan_status.update(
                        label=label,
                        state="running",
                        expanded=True,
                    )

                    scan_status.write(
                        event.get(
                            "message",
                            label,
                        )
                    )

                elif event_type == "repository_ready":
                    discovered = event.get(
                        "python_files_found",
                        0,
                    )

                    scan_status.write(
                        f"Found {discovered} readable "
                        "Python files."
                    )

                elif event_type == "bandit_complete":
                    total_files = int(
                        event.get(
                            "files_selected",
                            0,
                        )
                    )

                    candidate_findings = int(
                        event.get(
                            "candidate_findings",
                            0,
                        )
                    )

                    scan_status.write(
                        f"Bandit supplied "
                        f"{candidate_findings} candidate "
                        "finding(s) for AI verification."
                    )

                elif event_type == "file_started":
                    current_file = int(
                        event.get(
                            "current",
                            0,
                        )
                    )

                    total_files = int(
                        event.get(
                            "total",
                            total_files,
                        )
                    )

                    file_name = event.get(
                        "file",
                        "Python file",
                    )

                    activity_slot.markdown(
                        f"""
                        <div class="sr-live-activity">
                            <span class="sr-pulse"></span>
                            <div>
                                <strong>Reviewing {safe_text(file_name)}</strong>
                                <small>
                                    File {current_file} of {total_files}
                                </small>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    progress_value = (
                        (current_file - 1)
                        / max(
                            1,
                            total_files,
                        )
                    )

                    progress_bar.progress(
                        progress_value,
                        text=(
                            f"AI reviewing {file_name}"
                        ),
                    )

                elif (
                    event_type
                    == "ai_verification_started"
                ):
                    bandit_count = event.get(
                        "bandit_findings",
                        0,
                    )

                    rag_count = event.get(
                        "rag_guides",
                        0,
                    )

                    scan_status.update(
                        label=(
                            "Fine-tuned model verifying "
                            "source evidence"
                        ),
                        state="running",
                        expanded=True,
                    )

                    scan_status.write(
                        f"{event.get('file', 'File')}: "
                        f"{bandit_count} Bandit clue(s), "
                        f"{rag_count} RAG guide(s)."
                    )

                elif event_type == "ai_working":
                    elapsed = event.get(
                        "elapsed_seconds",
                        0,
                    )

                    activity_slot.markdown(
                        f"""
                        <div class="sr-live-activity">
                            <span class="sr-pulse"></span>
                            <div>
                                <strong>
                                    AI verification in progress
                                </strong>
                                <small>
                                    {safe_text(event.get("file", ""))}
                                    · {safe_text(elapsed)} seconds
                                </small>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                elif event_type == "finding":
                    finding = event.get(
                        "finding",
                        {},
                    )

                    findings_count += 1

                    feed_caption.caption(
                        f"{findings_count} validated "
                        "finding(s) streamed so far"
                    )

                    with finding_feed:
                        render_finding(
                            finding,
                            findings_count,
                            expanded=True,
                        )

                elif event_type == "file_complete":
                    completed_files += 1

                    current_file = int(
                        event.get(
                            "current",
                            current_file,
                        )
                    )

                    total_files = int(
                        event.get(
                            "total",
                            total_files,
                        )
                    )

                    progress_bar.progress(
                        current_file
                        / max(
                            1,
                            total_files,
                        ),
                        text=(
                            f"Completed "
                            f"{event.get('file', 'file')}"
                        ),
                    )

                elif event_type == "file_failed":
                    completed_files += 1

                    current_file = int(
                        event.get(
                            "current",
                            current_file,
                        )
                    )

                    total_files = int(
                        event.get(
                            "total",
                            total_files,
                        )
                    )

                    progress_bar.progress(
                        current_file
                        / max(
                            1,
                            total_files,
                        ),
                        text=(
                            f"Skipped "
                            f"{event.get('file', 'file')}"
                        ),
                    )

                    scan_status.warning(
                        f"Skipped "
                        f"{event.get('file', 'a file')}: "
                        f"{event.get('message', 'unknown error')}"
                    )

                elif event_type == "scan_complete":
                    final_report = event.get(
                        "report",
                        {},
                    )

                    st.session_state.current_report = (
                        final_report
                    )

                    analyzed_count = int(
                        final_report.get(
                            "files_analyzed",
                            0,
                        )
                        or 0
                    )

                    if analyzed_count > 0:
                        save_report(
                            final_report,
                            st.session_state.user_email,
                        )

                        st.session_state.selected_report_id = (
                            final_report.get(
                                "scan_id"
                            )
                        )

                        progress_bar.progress(
                            1.0,
                            text="Security report complete",
                        )

                        activity_slot.markdown(
                            """
                            <div class="sr-live-activity sr-live-complete">
                                <span>✓</span>
                                <div>
                                    <strong>Repository analysis complete</strong>
                                    <small>
                                        Report saved to local scan history
                                    </small>
                                </div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                        scan_status.update(
                            label=(
                                "Security analysis completed"
                            ),
                            state="complete",
                            expanded=False,
                        )

                    else:
                        scan_status.update(
                            label=(
                                "No files were analyzed"
                            ),
                            state="error",
                            expanded=True,
                        )

                elif event_type == "scan_error":
                    raise BackendScanError(
                        event.get(
                            "message",
                            "The backend could not complete the scan.",
                        )
                    )

                update_live_metrics(
                    metric_slot,
                    current_file,
                    total_files,
                    completed_files,
                    findings_count,
                    candidate_findings,
                )

    except (
        requests.RequestException,
        BackendScanError,
        ValueError,
        TypeError,
        sqlite3.Error,
    ) as error:
        scan_status.update(
            label="Security scan stopped",
            state="error",
            expanded=True,
        )

        st.error(
            str(error)
        )
        return None

    if final_report is None:
        scan_status.update(
            label="No final report received",
            state="error",
            expanded=True,
        )

        st.error(
            "The connection ended before Kaggle sent "
            "the final report."
        )
        return None

    return final_report


def render_new_scan():
    page_heading(
        "NEW ANALYSIS",
        "Scan a GitHub repository",
        (
            "Stream evidence-backed vulnerabilities from the "
            "Kaggle GPU as each Python file is validated."
        ),
    )

    health = check_backend(
        BACKEND_URL
    )

    backend_ready = bool(
        health.get("online")
        and health.get("ready")
    )

    status_class = (
        "online"
        if backend_ready
        else "offline"
    )

    status_text = (
        "Kaggle GPU backend connected"
        if backend_ready
        else (
            "Kaggle backend is still starting"
            if health.get("online")
            else "Kaggle backend is not connected"
        )
    )

    st.markdown(
        f"""
        <div class="sr-connection-banner sr-connection-{status_class}">
            <span class="sr-status-dot sr-{status_class}"></span>
            <div>
                <strong>{safe_text(status_text)}</strong>
                <small>
                    {
                        "Fine-tuned model and streaming API are ready."
                        if backend_ready
                        else (
                            "Run Kaggle Blocks 1–9 in order, "
                            "then update the local secrets file."
                        )
                    }
                </small>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        repository_url = st.text_input(
            "Public GitHub repository URL",
            placeholder=(
                "https://github.com/owner/repository"
            ),
            help=(
                "SecureRepo currently scans public GitHub "
                "repositories containing Python files."
            ),
        )

        option_columns = st.columns(
            [1, 2]
        )

        with option_columns[0]:
            file_limit = st.slider(
                "Maximum files",
                min_value=1,
                max_value=50,
                value=20,
                help=(
                    "Files with Bandit clues are analyzed first."
                ),
            )

        with option_columns[1]:
            st.markdown(
                """
                <div class="sr-readonly-note">
                    <strong>Read-only analysis</strong>
                    <span>
                        Repository source is cloned temporarily,
                        inspected and removed. It is never imported
                        or executed.
                    </span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        start_scan = st.button(
            "Start security scan",
            type="primary",
            use_container_width=True,
            disabled=not backend_ready,
        )

    if start_scan:
        if not repository_url.strip():
            st.error(
                "Enter a public GitHub repository URL."
            )
            return

        st.session_state.current_report = None

        completed_report = run_live_scan(
            repository_url.strip(),
            file_limit,
        )

        if completed_report is not None:
            st.session_state.current_report = (
                completed_report
            )

    completed_report = (
        st.session_state.get(
            "current_report"
        )
    )

    if completed_report is not None:
        st.divider()
        render_report(
            completed_report,
            key_prefix=(
                "live_"
                + completed_report.get(
                    "scan_id",
                    "report",
                )
            ),
        )


def build_repository_groups(history):
    repositories = {}

    for scan in history:
        repository = scan[
            "repository"
        ]

        if repository not in repositories:
            repositories[repository] = {
                "repository": repository,
                "repository_name": scan[
                    "repository_name"
                ],
                "scan_count": 0,
                "total_findings": 0,
                "latest_scan": scan,
                "highest_risk": 0,
            }

        group = repositories[
            repository
        ]

        group["scan_count"] += 1
        group["total_findings"] += (
            scan["total_findings"]
        )
        group["highest_risk"] = max(
            group["highest_risk"],
            scan["risk_score"],
        )

    return list(
        repositories.values()
    )


def render_repositories():
    page_heading(
        "REPOSITORY INVENTORY",
        "Monitored repositories",
        (
            "Review every repository analyzed in this "
            "local workspace and reopen its latest report."
        ),
    )

    history = get_scan_history(
        st.session_state.user_email
    )

    repositories = build_repository_groups(
        history
    )

    if not repositories:
        st.info(
            "No repositories have been scanned yet."
        )
        return

    search_query = st.text_input(
        "Search repositories",
        placeholder="Search by repository name or URL",
    ).strip().lower()

    for index, repository in enumerate(
        repositories
    ):
        searchable = (
            repository[
                "repository_name"
            ]
            + " "
            + repository["repository"]
        ).lower()

        if (
            search_query
            and search_query not in searchable
        ):
            continue

        latest = repository[
            "latest_scan"
        ]

        with st.container(border=True):
            columns = st.columns(
                [3.2, 1, 1, 1],
                vertical_alignment="center",
            )

            with columns[0]:
                st.markdown(
                    f"""
                    <div class="sr-repo-row">
                        <div class="sr-repo-icon">&lt;/&gt;</div>
                        <div>
                            <strong>
                                {safe_text(repository["repository_name"])}
                            </strong>
                            <span>
                                {safe_text(repository["repository"])}
                            </span>
                            <small>
                                Latest scan
                                {safe_text(format_time(latest["completed_at"]))}
                            </small>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            with columns[1]:
                metric_card(
                    "Scans",
                    repository[
                        "scan_count"
                    ],
                    "Completed",
                    "cyan",
                )

            with columns[2]:
                metric_card(
                    "Findings",
                    repository[
                        "total_findings"
                    ],
                    "All scans",
                    "red",
                )

            with columns[3]:
                st.button(
                    "Latest report",
                    key=f"repository_{index}",
                    use_container_width=True,
                    on_click=open_saved_report,
                    args=(
                        latest["scan_id"],
                    ),
                )


def render_scan_history():
    page_heading(
        "AUDIT TRAIL",
        "Scan history",
        (
            "Every completed report is stored locally "
            "and remains available when Kaggle disconnects."
        ),
    )

    history = get_scan_history(
        st.session_state.user_email
    )

    if not history:
        st.info(
            "Your scan history is empty."
        )
        return

    filter_columns = st.columns(
        [2, 1]
    )

    with filter_columns[0]:
        search_query = st.text_input(
            "Search history",
            placeholder="Repository name or URL",
        ).strip().lower()

    with filter_columns[1]:
        risk_filter = st.selectbox(
            "Risk level",
            [
                "All",
                "Critical",
                "High risk",
                "Medium risk",
                "Low risk",
                "No findings",
            ],
        )

    shown = 0

    for index, scan in enumerate(
        history
    ):
        searchable = (
            scan["repository_name"]
            + " "
            + scan["repository"]
        ).lower()

        if (
            search_query
            and search_query not in searchable
        ):
            continue

        if (
            risk_filter != "All"
            and risk_label(
                scan["risk_score"]
            )
            != risk_filter
        ):
            continue

        render_scan_card(
            scan,
            button_key=f"history_report_{index}",
        )
        shown += 1

    if shown == 0:
        st.info(
            "No scans match the current filters."
        )


def render_reports():
    page_heading(
        "SECURITY INTELLIGENCE",
        "Validated reports",
        (
            "Inspect confirmed findings, evidence, impact "
            "and safer replacement code."
        ),
    )

    history = get_scan_history(
        st.session_state.user_email
    )

    if not history:
        st.info(
            "Complete a repository scan to create a report."
        )
        return

    scan_ids = [
        scan["scan_id"]
        for scan in history
    ]

    selected_id = st.session_state.get(
        "selected_report_id"
    )

    if selected_id not in scan_ids:
        selected_id = scan_ids[0]

    selected_index = scan_ids.index(
        selected_id
    )

    selected_scan_id = st.selectbox(
        "Choose a completed scan",
        options=scan_ids,
        index=selected_index,
        format_func=lambda scan_id: next(
            (
                f"{scan['repository_name']} — "
                f"{format_time(scan['completed_at'])}"
                for scan in history
                if scan["scan_id"] == scan_id
            ),
            scan_id,
        ),
    )

    st.session_state.selected_report_id = (
        selected_scan_id
    )

    report = get_saved_report(
        selected_scan_id,
        st.session_state.user_email,
    )

    if report is None:
        st.error(
            "The selected report could not be loaded."
        )
        return

    render_report(
        report,
        key_prefix=(
            "saved_"
            + selected_scan_id
        ),
    )


def render_settings():
    page_heading(
        "WORKSPACE",
        "System settings",
        (
            "Review the connection between this local "
            "interface and the Kaggle GPU backend."
        ),
    )

    health = check_backend(
        BACKEND_URL
    )

    backend_ready = bool(
        health.get("online")
        and health.get("ready")
    )

    connection_columns = st.columns(3)

    with connection_columns[0]:
        metric_card(
            "Backend",
            (
                "Ready"
                if backend_ready
                else (
                    "Starting"
                    if health.get("online")
                    else "Offline"
                )
            ),
            "Kaggle through ngrok",
            (
                "cyan"
                if backend_ready
                else "red"
            ),
        )

    with connection_columns[1]:
        metric_card(
            "GPU",
            (
                "Available"
                if health.get(
                    "gpu_available"
                )
                else "Unavailable"
            ),
            "Model inference",
            "violet",
        )

    with connection_columns[2]:
        metric_card(
            "Scan engine",
            (
                "Busy"
                if health.get(
                    "scan_in_progress"
                )
                else "Ready"
            ),
            "One scan at a time",
            "orange",
        )

    st.markdown(
        "### Connection"
    )

    with st.container(border=True):
        backend_host = (
            urlparse(
                BACKEND_URL
            ).netloc
            if BACKEND_URL
            else "Not configured"
        )

        st.markdown(
            f"**Backend host:** `{backend_host}`"
        )
        st.markdown(
            "**API key:** "
            + (
                "Configured securely"
                if API_KEY
                else "Missing"
            )
        )

        st.markdown(
            "**Local history:** SQLite active"
        )

        if st.button(
            "Retest backend connection",
        ):
            check_backend.clear()
            st.rerun()

    st.markdown(
        "### Architecture"
    )

    st.markdown(
        """
        <div class="sr-architecture">
            <div>
                <strong>Local Streamlit</strong>
                <span>Interface + SQLite history</span>
            </div>
            <i>→</i>
            <div>
                <strong>ngrok tunnel</strong>
                <span>Private API connection</span>
            </div>
            <i>→</i>
            <div>
                <strong>Kaggle GPU</strong>
                <span>Bandit + RAG + LoRA + Pydantic</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.info(
        "Login and registration are visual placeholders "
        "for the competition demo. They are not production "
        "authentication."
    )


if not st.session_state.authenticated:
    render_login()
    st.stop()


render_sidebar()


page_renderers = {
    "Overview": render_overview,
    "New Scan": render_new_scan,
    "Repositories": render_repositories,
    "Scan History": render_scan_history,
    "Reports": render_reports,
    "Settings": render_settings,
}


selected_page = st.session_state.navigation
page_renderers.get(
    selected_page,
    render_overview,
)()


st.markdown(
    """
    <div class="sr-footer">
        SecureRepo AI · Defensive, read-only security analysis
    </div>
    """,
    unsafe_allow_html=True,
)
