"""Shared Streamlit CSS snippets for the admin console."""

from __future__ import annotations


def build_admin_console_css() -> str:
    """Return the base CSS used by the admin login and dashboard pages."""
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
      --warning-500: #E5A23A;
      --danger-500: #D84C4C;
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

    .xinyu-sync-chip {
      display: inline-flex;
      align-items: center;
      margin-top: 10px;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(47, 143, 131, 0.1);
      color: var(--brand-700);
      font-size: 12px;
      font-weight: 600;
    }

    .xinyu-topbar-title {
      margin: 8px 0 0 0;
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

    .xinyu-kpi-card {
      padding: 20px;
      border-radius: var(--radius-md);
      background: rgba(255, 255, 255, 0.9);
      border: 1px solid #E3EAE7;
      border-top: 4px solid var(--brand-500);
      box-shadow: var(--shadow-card);
      min-height: 152px;
    }

    .xinyu-kpi-warning {
      border-top-color: var(--warning-500);
    }

    .xinyu-kpi-danger {
      border-top-color: var(--danger-500);
    }

    .xinyu-kpi-brand {
      border-top-color: var(--brand-500);
    }

    .xinyu-kpi-neutral {
      border-top-color: var(--neutral-300);
    }

    .xinyu-kpi-value {
      color: var(--neutral-900);
      font-family: "DIN Alternate", "SF Mono", monospace;
      font-size: 32px;
      font-weight: 700;
      line-height: 1.2;
    }

    .xinyu-kpi-label {
      margin-top: 8px;
      color: var(--neutral-900);
      font-size: 16px;
      font-weight: 600;
      line-height: 1.4;
    }

    .xinyu-kpi-meta {
      margin-top: 8px;
      color: var(--neutral-500);
      font-size: 13px;
      line-height: 1.5;
    }

    .xinyu-stat-card {
      padding: 18px 20px;
      border-radius: var(--radius-md);
      background: rgba(255, 255, 255, 0.88);
      border: 1px solid #E3EAE7;
      min-height: 136px;
    }

    .xinyu-stat-value {
      color: var(--neutral-900);
      font-family: "DIN Alternate", "SF Mono", monospace;
      font-size: 24px;
      font-weight: 700;
      line-height: 1.2;
    }

    .xinyu-stat-label {
      margin-top: 10px;
      color: var(--neutral-900);
      font-size: 15px;
      font-weight: 600;
      line-height: 1.4;
    }

    .xinyu-stat-meta {
      margin-top: 8px;
      color: var(--neutral-500);
      font-size: 13px;
      line-height: 1.5;
    }

    .xinyu-nav-card {
      padding: 20px;
      border-radius: var(--radius-lg);
      background: rgba(255, 255, 255, 0.9);
      border: 1px solid #E3EAE7;
      box-shadow: var(--shadow-card);
      min-height: 196px;
    }

    .xinyu-nav-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }

    .xinyu-nav-step {
      display: inline-flex;
      align-items: center;
      padding: 6px 10px;
      border-radius: 999px;
      background: var(--brand-50);
      color: var(--brand-700);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }

    .xinyu-nav-status {
      color: var(--neutral-500);
      font-size: 12px;
      font-weight: 600;
    }

    .xinyu-nav-title {
      margin-top: 14px;
      color: var(--neutral-900);
      font-size: 18px;
      font-weight: 600;
      line-height: 1.3;
    }

    .xinyu-nav-copy {
      margin-top: 10px;
      color: var(--neutral-700);
      font-size: 14px;
      line-height: 1.5;
    }

    .xinyu-nav-metric {
      margin-top: 16px;
      padding-top: 14px;
      border-top: 1px solid var(--neutral-100);
      color: var(--brand-700);
      font-size: 13px;
      font-weight: 600;
      line-height: 1.5;
    }

    .xinyu-chart-header {
      margin-bottom: 8px;
    }

    .xinyu-chart-eyebrow {
      color: var(--neutral-500);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }

    .xinyu-chart-title {
      margin-top: 8px;
      color: var(--neutral-900);
      font-size: 18px;
      font-weight: 600;
      line-height: 1.3;
    }

    .xinyu-chart-copy {
      margin-top: 8px;
      color: var(--neutral-700);
      font-size: 14px;
      line-height: 1.6;
    }

    .xinyu-empty-state {
      margin-top: 8px;
      padding: 24px;
      border-radius: var(--radius-lg);
      background: rgba(255, 255, 255, 0.92);
      border: 1px solid rgba(216, 76, 76, 0.18);
      box-shadow: var(--shadow-card);
    }

    .xinyu-empty-title {
      color: var(--neutral-900);
      font-size: 18px;
      font-weight: 600;
      line-height: 1.3;
    }

    .xinyu-empty-copy {
      margin: 10px 0 0 0;
      color: var(--neutral-700);
      font-size: 14px;
      line-height: 1.5;
    }

    .xinyu-alert-card {
      margin-bottom: 12px;
      padding: 18px 18px 16px 18px;
      border-radius: var(--radius-md);
      background: rgba(255, 255, 255, 0.9);
      border: 1px solid #E3EAE7;
      box-shadow: var(--shadow-card);
    }

    .xinyu-alert-card-active {
      border-color: rgba(47, 143, 131, 0.5);
      box-shadow: 0 12px 28px rgba(30, 100, 92, 0.12);
    }

    .xinyu-alert-card-header {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    .xinyu-alert-card-title {
      color: var(--neutral-900);
      font-size: 16px;
      font-weight: 600;
      line-height: 1.4;
    }

    .xinyu-alert-card-meta {
      color: var(--neutral-500);
      font-size: 12px;
      line-height: 1.4;
    }

    .xinyu-chip-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 12px;
    }

    .xinyu-chip {
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      padding: 0 10px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 600;
      line-height: 1;
    }

    .xinyu-chip-brand {
      background: rgba(47, 143, 131, 0.12);
      color: var(--brand-700);
    }

    .xinyu-chip-warning {
      background: rgba(229, 162, 58, 0.14);
      color: #9C650A;
    }

    .xinyu-chip-danger {
      background: rgba(216, 76, 76, 0.12);
      color: #A92A2A;
    }

    .xinyu-chip-neutral {
      background: rgba(112, 128, 124, 0.12);
      color: var(--neutral-700);
    }

    .xinyu-chip-success {
      background: rgba(61, 155, 94, 0.12);
      color: #2F7D49;
    }

    .xinyu-alert-card-copy {
      margin-top: 12px;
      color: var(--neutral-700);
      font-size: 14px;
      line-height: 1.5;
    }

    .xinyu-alert-card-foot {
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid var(--neutral-100);
      color: var(--neutral-500);
      font-size: 12px;
      line-height: 1.5;
    }

    .xinyu-detail-card,
    .xinyu-section-card,
    .xinyu-history-card,
    .xinyu-timeline-item,
    .xinyu-copy-block {
      margin-bottom: 12px;
      padding: 18px 20px;
      border-radius: var(--radius-md);
      background: rgba(255, 255, 255, 0.92);
      border: 1px solid #E3EAE7;
      box-shadow: var(--shadow-card);
    }

    .xinyu-detail-title,
    .xinyu-section-title,
    .xinyu-history-title,
    .xinyu-timeline-title,
    .xinyu-copy-block-title {
      color: var(--neutral-900);
      font-size: 17px;
      font-weight: 600;
      line-height: 1.4;
    }

    .xinyu-detail-copy,
    .xinyu-section-copy,
    .xinyu-history-copy,
    .xinyu-timeline-copy,
    .xinyu-copy-block-body {
      margin-top: 10px;
      color: var(--neutral-700);
      font-size: 14px;
      line-height: 1.6;
    }

    .xinyu-detail-foot,
    .xinyu-history-foot,
    .xinyu-timeline-foot {
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid var(--neutral-100);
      color: var(--neutral-500);
      font-size: 12px;
      line-height: 1.5;
    }

    .xinyu-section-label {
      color: var(--neutral-500);
      font-size: 12px;
      font-weight: 600;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }

    .xinyu-copy-block-brand {
      border-left: 4px solid var(--brand-500);
    }

    .xinyu-copy-block-warning {
      border-left: 4px solid var(--warning-500);
      background: rgba(255, 241, 227, 0.62);
    }

    .xinyu-copy-block-danger {
      border-left: 4px solid var(--danger-500);
      background: rgba(251, 231, 231, 0.72);
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

    .stTextArea textarea,
    .stSelectbox div[data-baseweb="select"] > div {
      border-radius: 14px;
      border: 1px solid #E3EAE7;
      background: rgba(248, 250, 250, 0.95);
      color: var(--neutral-900);
    }

    div[data-testid="stDataFrame"] {
      border-radius: 14px;
      overflow: hidden;
      border: 1px solid #E3EAE7;
      background: rgba(255, 255, 255, 0.96);
    }
    </style>
    """
