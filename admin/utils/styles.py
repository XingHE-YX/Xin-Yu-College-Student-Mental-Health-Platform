"""Shared Streamlit CSS snippets for the admin console."""

from __future__ import annotations


def build_admin_console_css() -> str:
    """Return the base CSS used by the Streamlit admin shell."""
    return """
    <style>
    :root {
      --brand-50: #EEF7F5;
      --brand-100: #D7ECE6;
      --brand-500: #2F8F83;
      --brand-700: #1E645C;
      --neutral-0: #FFFFFF;
      --neutral-50: #F8FAFA;
      --neutral-100: #EEF2F1;
      --neutral-300: #C5CFCD;
      --neutral-500: #70807C;
      --neutral-700: #41504C;
      --neutral-900: #1F2A28;
      --danger-500: #D84C4C;
      --warning-500: #E5A23A;
      --shadow-card: 0 8px 24px rgba(18, 63, 58, 0.08);
      --radius-md: 14px;
      --radius-lg: 20px;
    }

    .stApp {
      background:
        radial-gradient(circle at top left, rgba(215, 236, 230, 0.7), transparent 28%),
        linear-gradient(180deg, #F8FAFA 0%, #EEF7F5 100%);
      color: var(--neutral-900);
      font-family: "Inter", "PingFang SC", "Microsoft YaHei", sans-serif;
    }

    .block-container {
      max-width: 1280px;
      padding-top: 2rem;
      padding-bottom: 2rem;
    }

    .xinyu-auth-shell {
      min-height: 78vh;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .xinyu-auth-card {
      width: min(100%, 480px);
      padding: 32px;
      border-radius: var(--radius-lg);
      background: rgba(255, 255, 255, 0.92);
      border: 1px solid #E3EAE7;
      box-shadow: var(--shadow-card);
      backdrop-filter: blur(12px);
    }

    .xinyu-auth-eyebrow {
      display: inline-block;
      margin-bottom: 12px;
      padding: 6px 10px;
      border-radius: 999px;
      background: var(--brand-50);
      color: var(--brand-700);
      font-size: 12px;
      font-weight: 600;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }

    .xinyu-auth-title {
      margin: 0 0 8px 0;
      color: var(--neutral-900);
      font-size: 28px;
      font-weight: 700;
      line-height: 1.2;
    }

    .xinyu-auth-copy {
      margin: 0 0 20px 0;
      color: var(--neutral-700);
      font-size: 15px;
      line-height: 1.5;
    }

    .xinyu-hint-card {
      margin-top: 18px;
      padding: 14px 16px;
      border-radius: var(--radius-md);
      border: 1px solid rgba(229, 162, 58, 0.16);
      background: rgba(255, 241, 227, 0.9);
      color: #7B5A2E;
      font-size: 13px;
      line-height: 1.5;
    }

    .xinyu-topbar {
      margin-bottom: 24px;
      padding: 20px 24px;
      border-radius: var(--radius-lg);
      background: rgba(255, 255, 255, 0.92);
      border: 1px solid #E3EAE7;
      box-shadow: var(--shadow-card);
    }

    .xinyu-topbar-label {
      color: var(--neutral-500);
      font-size: 12px;
      font-weight: 600;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }

    .xinyu-topbar-title {
      margin: 6px 0 0 0;
      color: var(--neutral-900);
      font-size: 24px;
      font-weight: 600;
      line-height: 1.3;
    }

    .xinyu-topbar-copy {
      margin: 10px 0 0 0;
      color: var(--neutral-700);
      font-size: 14px;
      line-height: 1.5;
    }

    .xinyu-placeholder-card {
      padding: 20px;
      border-radius: var(--radius-md);
      background: rgba(255, 255, 255, 0.9);
      border: 1px solid #E3EAE7;
      box-shadow: var(--shadow-card);
      min-height: 148px;
    }

    .xinyu-placeholder-kpi {
      color: var(--neutral-900);
      font-family: "DIN Alternate", "SF Mono", monospace;
      font-size: 32px;
      font-weight: 700;
      line-height: 1.2;
    }

    .xinyu-placeholder-label {
      margin-top: 6px;
      color: var(--neutral-500);
      font-size: 13px;
      line-height: 1.4;
    }

    .stButton > button {
      min-height: 48px;
      border-radius: 14px;
      border: none;
      background: var(--brand-500);
      color: white;
      font-weight: 600;
    }

    .stButton > button:hover {
      background: var(--brand-700);
      color: white;
    }

    .stTextInput input {
      min-height: 48px;
      border-radius: 14px;
      border: 1px solid #E3EAE7;
      background: rgba(248, 250, 250, 0.95);
      color: var(--neutral-900);
    }
    </style>
    """
