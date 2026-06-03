from __future__ import annotations

import hmac

import streamlit as st

from ..config import dashboard_auth_required, dashboard_password, dashboard_username


def verify_dashboard_credentials(username: str, password: str) -> bool:
    """Constant-time check against DASHBOARD_USERNAME / DASHBOARD_PASSWORD env."""
    expected_password = dashboard_password()
    if not expected_password.strip():
        return True

    if not hmac.compare_digest(password.encode("utf-8"), expected_password.encode("utf-8")):
        return False

    expected_username = dashboard_username()
    if not expected_username:
        return True

    return hmac.compare_digest(username.encode("utf-8"), expected_username.encode("utf-8"))


def ensure_dashboard_authenticated() -> None:
    """Show login form and stop the app until credentials are valid."""
    if not dashboard_auth_required():
        return

    if st.session_state.get("dashboard_authenticated"):
        return

    st.title("Congress Trading Dashboard")
    st.caption("Sign in to continue.")

    with st.form("dashboard_login", clear_on_submit=False):
        username = st.text_input("Username", autocomplete="username")
        password = st.text_input("Password", type="password", autocomplete="current-password")
        submitted = st.form_submit_button("Sign in")

    if submitted:
        if verify_dashboard_credentials(username.strip(), password):
            st.session_state["dashboard_authenticated"] = True
            st.rerun()
        else:
            st.error("Invalid username or password.")

    st.stop()
