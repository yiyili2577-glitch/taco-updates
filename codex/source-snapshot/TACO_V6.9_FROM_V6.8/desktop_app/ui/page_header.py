from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout


def add_page_header(layout, title: str, subtitle: str = ""):
    """Add a consistent ERP page header without changing page business logic."""
    frame = QFrame()
    frame.setObjectName("pageHeader")
    inner = QVBoxLayout(frame)
    inner.setContentsMargins(14, 10, 14, 10)
    inner.setSpacing(3)

    title_label = QLabel(title)
    title_label.setObjectName("pageTitle")
    inner.addWidget(title_label)

    if subtitle:
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("pageSubtitle")
        subtitle_label.setWordWrap(True)
        inner.addWidget(subtitle_label)

    layout.addWidget(frame)
    return frame
