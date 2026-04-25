"""
Programmatic UI layout for the main window.
No .ui file needed – everything is built with PySide6 widgets.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMenuBar,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)


class Ui_MainWindow:
    """Sets up all widgets on the given QMainWindow."""

    def setup_ui(self, win: QMainWindow) -> None:
        win.setWindowTitle("Dataverse OptionSet Helper")
        win.resize(1200, 750)

        # ── Menu bar ─────────────────────────────────────────────────
        self.menu_bar = QMenuBar(win)
        win.setMenuBar(self.menu_bar)

        # File menu
        self.menu_file = QMenu("&File", win)
        self.action_settings = QAction("⚙  &Settings …", win)
        self.action_quit = QAction("&Quit", win)
        self.action_quit.setShortcut("Ctrl+Q")
        self.menu_file.addAction(self.action_settings)
        self.menu_file.addSeparator()
        self.menu_file.addAction(self.action_quit)
        self.menu_bar.addMenu(self.menu_file)

        # Actions menu
        self.menu_actions = QMenu("&Actions", win)
        self.action_refresh = QAction("🔄  &Refresh list", win)
        self.action_refresh.setShortcut("F5")
        self.action_create_global = QAction("➕  &Create global OptionSet …", win)
        self.action_insert_single = QAction("📝  Insert &single option …", win)
        self.action_bulk_insert = QAction("📥  Bulk &Insert (file) …", win)
        self.action_bulk_update = QAction("📤  Bulk &Update (file) …", win)
        self.action_bulk_delete = QAction("🗑  Bulk &Delete (file) …", win)
        for a in (
            self.action_refresh,
            self.action_create_global,
            self.action_insert_single,
            self.action_bulk_insert,
            self.action_bulk_update,
            self.action_bulk_delete,
        ):
            self.menu_actions.addAction(a)
        self.menu_bar.addMenu(self.menu_actions)

        # ── Toolbar ──────────────────────────────────────────────────
        self.toolbar = QToolBar("Main Toolbar", win)
        self.toolbar.setMovable(False)
        win.addToolBar(self.toolbar)
        self.toolbar.addAction(self.action_refresh)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.action_create_global)
        self.toolbar.addAction(self.action_insert_single)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.action_bulk_insert)
        self.toolbar.addAction(self.action_bulk_update)
        self.toolbar.addAction(self.action_bulk_delete)

        # ── Central widget ───────────────────────────────────────────
        central = QWidget(win)
        win.setCentralWidget(central)
        root_layout = QVBoxLayout(central)

        # Splitter: left (list) | right (detail)
        splitter = QSplitter(Qt.Orientation.Horizontal, central)
        root_layout.addWidget(splitter, stretch=1)

        # -- LEFT panel: search + global optionsets table -------------
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Search bar
        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search OptionSets …")
        self.btn_search = QPushButton("Search")
        search_row.addWidget(self.search_input, stretch=1)
        search_row.addWidget(self.btn_search)
        left_layout.addLayout(search_row)

        # OptionSets table
        self.tbl_optionsets = QTableWidget(0, 4)
        self.tbl_optionsets.setHorizontalHeaderLabels(
            ["Name", "Display Label", "Type", "# Options"]
        )
        self.tbl_optionsets.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.tbl_optionsets.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.tbl_optionsets.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.tbl_optionsets.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.tbl_optionsets.setAlternatingRowColors(True)
        left_layout.addWidget(self.tbl_optionsets)

        splitter.addWidget(left_widget)

        # -- RIGHT panel: options detail table ------------------------
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.lbl_detail_title = QLabel("Select an OptionSet on the left")
        self.lbl_detail_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        right_layout.addWidget(self.lbl_detail_title)

        # Options search bar
        options_search_row = QHBoxLayout()
        self.options_search_input = QLineEdit()
        self.options_search_input.setPlaceholderText("Filter by label or value …")
        self.btn_options_search = QPushButton("Filter")
        options_search_row.addWidget(self.options_search_input, stretch=1)
        options_search_row.addWidget(self.btn_options_search)
        right_layout.addLayout(options_search_row)

        self.tbl_options = QTableWidget(0, 2)
        self.tbl_options.setHorizontalHeaderLabels(["Value", "Label"])
        self.tbl_options.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.tbl_options.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.tbl_options.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.tbl_options.setAlternatingRowColors(True)
        self.tbl_options.setSortingEnabled(True)
        right_layout.addWidget(self.tbl_options)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        # ── Log panel (bottom) ───────────────────────────────────────
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumHeight(160)
        self.log_output.setPlaceholderText("Activity log …")
        root_layout.addWidget(self.log_output)

        # ── Status bar ───────────────────────────────────────────────
        self.status_bar = QStatusBar(win)
        win.setStatusBar(self.status_bar)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(260)
        self.progress_bar.setVisible(False)
        self.status_bar.addPermanentWidget(self.progress_bar)

        self.lbl_status = QLabel("Ready")
        self.status_bar.addWidget(self.lbl_status)
