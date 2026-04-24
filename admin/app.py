"""Streamlit admin console entrypoint placeholder."""


def main() -> None:
    """Render a minimal bootstrap page before feature implementation."""
    try:
        import streamlit as st
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Streamlit is not installed in the current environment.") from exc

    st.set_page_config(page_title="心语管理后台", layout="wide")
    st.title("心语管理后台")
    st.info("项目已完成初始化。具体后台页面将在后续实施步骤中构建。")


if __name__ == "__main__":
    main()
