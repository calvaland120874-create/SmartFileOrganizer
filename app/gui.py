"""PySide6 dashboard interface for Smart File Organizer."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QObject, QPropertyAnimation, QRectF, QThread, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QGraphicsOpacityEffect,
    QApplication,
    QMenu,
    QSizePolicy,
    QSpacerItem,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QSystemTrayIcon,
    QStyle,
)

from app.organizer import CATEGORY_EXTENSIONS, DashboardSnapshot, FileOrganizer, InventorySnapshot, OrganizedFile
from app import startup


TYPE_COLORS = {
    "Images": "#2f7df6",
    "Documents": "#34c77b",
    "Videos": "#8058e6",
    "Music": "#ffb133",
    "PDF": "#f4b63d",
    "Compressed": "#ff6b18",
    "Executables": "#ff5370",
    "Code": "#23c5a2",
    "Others": "#8b98a8",
    "None": "#8b98a8",
}


class SmartFileOrganizerWindow(QMainWindow):
    """Main Qt window for the Smart File Organizer dashboard."""

    def __init__(self, start_in_background: bool = False) -> None:
        """Create the dashboard and load live system data."""
        super().__init__()
        self.start_in_background = start_in_background
        self.organizer = FileOrganizer()
        self.ensure_startup_registration()
        self.snapshot = self.organizer.snapshot()
        self.moved_this_session = 0
        self.monitoring_enabled = self.organizer.config.load().auto_organize
        self.nav_buttons: list[QPushButton] = []

        self.setWindowTitle("Organizador inteligente de archivos")
        self.resize(1360, 820)
        self.setMinimumSize(1120, 720)
        self.setStyleSheet(DARK_STYLESHEET)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.monitor_tick)

        self.stack = QStackedWidget()
        self.stat_total = QLabel()
        self.stat_today = QLabel()
        self.stat_folders = QLabel()
        self.stat_status = QLabel()
        self.stat_size = QLabel()
        self.stat_common = QLabel("Analizando...")
        self.activity_list = QListWidget()
        self.file_locations_list = QListWidget()
        self.dashboard_folder_list = QListWidget()
        self.folder_list = QListWidget()
        self.selected_folder_label = QLabel("Selecciona una carpeta para eliminarla.")
        self.folder_input = QLineEdit()
        self.stats_type_list = QListWidget()
        self.extension_list = QListWidget()
        self.largest_files_list = QListWidget()
        self.inventory_meta_label = QLabel("Analisis pendiente.")
        self.status_label = QLabel()
        self.logs_label = QLabel("Logs: logs/smart_organizer.log")
        self.history_table = QTableWidget(0, 5)
        self.history_search = QLineEdit()
        self.logs_view = QTextEdit()
        self.rules_table = QTableWidget(0, 2)
        self.auto_check = QCheckBox("Organizar automaticamente mientras la app esta abierta")
        self.startup_check = QCheckBox("Iniciar con Windows en segundo plano, sin consola")
        self.interval_spin = QSpinBox()
        self.monitor_title = QLabel()
        self.monitor_description = QLabel()
        self.monitor_button = QPushButton()
        self.inventory: InventorySnapshot | None = None
        self.inventory_thread: QThread | None = None
        self.inventory_worker: HomeInventoryWorker | None = None
        self.fade_animation: QPropertyAnimation | None = None
        self.tray_icon: QSystemTrayIcon | None = None

        self.setCentralWidget(self._build_root())
        self.setup_tray_icon()
        self.dashboard_folder_list.itemDoubleClicked.connect(self.open_selected_folder)
        self.folder_list.itemDoubleClicked.connect(self.open_selected_folder)
        self.folder_list.currentItemChanged.connect(self.update_selected_folder_label)
        self.history_search.textChanged.connect(self.render_history)
        self.apply_timer_settings()
        self.refresh()
        QTimer.singleShot(300, self.start_home_scan)

    def ensure_startup_registration(self) -> None:
        """Automatically enable Windows startup when the setting is on."""
        settings = self.organizer.config.load()
        if not settings.start_with_windows or not startup.is_supported():
            return
        try:
            if not startup.is_enabled():
                startup.enable()
        except OSError:
            return

    def _build_root(self) -> QWidget:
        """Build the full application layout."""
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar())
        layout.addWidget(self._build_pages(), 1)
        return root

    def _build_sidebar(self) -> QWidget:
        """Build the left navigation area."""
        sidebar = QFrame(objectName="Sidebar")
        sidebar.setFixedWidth(274)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(18, 28, 16, 22)
        layout.setSpacing(12)

        brand = QLabel("<b>Organizador inteligente</b><br><span>Organiza tus archivos</span>")
        brand.setObjectName("Brand")
        layout.addWidget(brand)

        nav_items = [
            "Dashboard",
            "Carpetas Monitoreadas",
            "Reglas de Organizacion",
            "Extensiones y Archivos Pesados",
            "Historial",
            "Logs",
            "Configuracion",
            "Temas",
            "Acerca de",
        ]
        for index, text in enumerate(nav_items):
            button = QPushButton(text)
            button.setObjectName("NavActive" if index == 0 else "NavButton")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda checked=False, page=index: self.switch_page(page))
            self.nav_buttons.append(button)
            layout.addWidget(button)

        layout.addItem(QSpacerItem(1, 1, QSizePolicy.Minimum, QSizePolicy.Expanding))

        monitor = QFrame(objectName="Panel")
        monitor_layout = QVBoxLayout(monitor)
        monitor_layout.setContentsMargins(18, 16, 18, 18)
        self.monitor_title.setText("<b>Monitoreo Activo</b>")
        self.monitor_description.setWordWrap(True)
        self.monitor_button.clicked.connect(self.toggle_monitoring)
        minimize_button = QPushButton("Minimizar")
        minimize_button.setObjectName("SecondaryButton")
        minimize_button.clicked.connect(self.showMinimized)
        monitor_layout.addWidget(self.monitor_title)
        monitor_layout.addWidget(self.monitor_description)
        monitor_layout.addWidget(self.monitor_button)
        monitor_layout.addWidget(minimize_button)
        layout.addWidget(monitor)

        layout.addWidget(QLabel("v1.0.0"))
        return sidebar

    def _build_pages(self) -> QWidget:
        """Build every page in the main stack."""
        page = QWidget(objectName="Page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 18)
        layout.setSpacing(0)
        self.stack.addWidget(self._dashboard_page())
        self.stack.addWidget(self._folders_page())
        self.stack.addWidget(self._rules_page())
        self.stack.addWidget(self._stats_page())
        self.stack.addWidget(self._history_page())
        self.stack.addWidget(self._logs_page())
        self.stack.addWidget(self._settings_page())
        self.stack.addWidget(self._themes_page())
        self.stack.addWidget(self._about_page())
        layout.addWidget(self.stack)
        return page

    def _page_shell(self, title: str, subtitle: str) -> tuple[QWidget, QVBoxLayout]:
        """Create a standard page with heading."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        heading = QLabel(f"<h1>{title}</h1><span>{subtitle}</span>")
        heading.setObjectName("PageTitle")
        layout.addWidget(heading)
        return page, layout

    def _dashboard_page(self) -> QWidget:
        """Build the dashboard page."""
        page, layout = self._page_shell("Dashboard", "Resumen general del estado de la aplicacion")
        header = QHBoxLayout()
        header.addStretch(1)
        config_button = QPushButton("Abrir Configuracion")
        config_button.setObjectName("SecondaryButton")
        config_button.clicked.connect(lambda: self.switch_page(6))
        refresh_button = QPushButton("Actualizar")
        refresh_button.setObjectName("SecondaryButton")
        refresh_button.clicked.connect(self.refresh)
        organize_button = QPushButton("Organizar ahora")
        organize_button.setObjectName("PrimaryButton")
        organize_button.clicked.connect(self.organize_now)
        header.addWidget(config_button)
        header.addWidget(refresh_button)
        header.addWidget(organize_button)
        layout.addLayout(header)

        cards = QGridLayout()
        cards.setHorizontalSpacing(14)
        self._add_stat_card(cards, 0, "Archivos en /home", self.stat_total, "Perfil del usuario")
        self._add_stat_card(cards, 1, "Organizados hoy", self.stat_today, "Historial del dia")
        self._add_stat_card(cards, 2, "Carpetas monitoreadas", self.stat_folders, "Desde tu sistema")
        self._add_stat_card(cards, 3, "Peso analizado", self.stat_size, "Total accesible")
        layout.addLayout(cards)

        middle = QGridLayout()
        middle.setHorizontalSpacing(14)
        middle.setVerticalSpacing(18)
        middle.addWidget(self._build_activity_panel(), 1, 0, 1, 2)
        middle.addWidget(self._build_folders_panel(), 2, 0)
        middle.addWidget(self._build_file_locations_panel(), 2, 1)
        middle.setColumnStretch(0, 1)
        middle.setColumnStretch(1, 1)
        layout.addLayout(middle, 0)

        status = QHBoxLayout()
        self.status_label.setObjectName("Muted")
        self.logs_label.setObjectName("Muted")
        self.stat_status.setObjectName("Success")
        status.addWidget(self.status_label)
        status.addWidget(self.logs_label)
        status.addWidget(self.stat_status)
        layout.addLayout(status)
        return page

    def _folders_page(self) -> QWidget:
        """Build the folder management page."""
        page, layout = self._page_shell("Carpetas Monitoreadas", "Agrega, abre o elimina carpetas del sistema")
        layout.addWidget(self._build_folder_manager_panel(), 1)
        row = QHBoxLayout()
        open_button = QPushButton("Abrir seleccionada")
        open_button.setObjectName("SecondaryButton")
        open_button.clicked.connect(self.open_current_folder)
        remove_button = QPushButton("Eliminar seleccionada")
        remove_button.setObjectName("DangerButton")
        remove_button.clicked.connect(self.remove_selected_folder)
        remove_all_button = QPushButton("Eliminar todas")
        remove_all_button.setObjectName("DangerButton")
        remove_all_button.clicked.connect(self.remove_all_folders)
        row.addStretch(1)
        row.addWidget(open_button)
        row.addWidget(remove_button)
        row.addWidget(remove_all_button)
        layout.addLayout(row)
        return page

    def _rules_page(self) -> QWidget:
        """Build the organization rules page."""
        page, layout = self._page_shell("Reglas de Organizacion", "Extensiones que usa el organizador")
        self.rules_table.setObjectName("Table")
        self.rules_table.setHorizontalHeaderLabels(["Categoria", "Extensiones"])
        self.rules_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.rules_table, 1)
        return page

    def _stats_page(self) -> QWidget:
        """Build the statistics page."""
        page, layout = self._page_shell("Archivos pesados y extensiones", "Analisis completo de los archivos en las carpetas monitoreadas")
        row = QHBoxLayout()
        analyze = QPushButton("Analizar /home ahora")
        analyze.setObjectName("PrimaryButton")
        analyze.clicked.connect(self.start_home_scan)
        row.addStretch(1)
        row.addWidget(analyze)
        layout.addLayout(row)
        grid = QGridLayout()
        grid.addWidget(self._build_extensions_panel(), 1, 0)
        grid.addWidget(self._build_largest_files_panel(), 1, 1)
        layout.addLayout(grid, 1)
        return page

    def _history_page(self) -> QWidget:
        """Build the history page."""
        page, layout = self._page_shell("Historial", "Busca archivos organizados por nombre, fecha o categoria")
        self.history_search.setPlaceholderText("Buscar en historial...")
        self.history_table.setObjectName("Table")
        self.history_table.setHorizontalHeaderLabels(["Fecha", "Archivo", "Categoria", "Origen", "Destino"])
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        row = QHBoxLayout()
        clear = QPushButton("Limpiar historial")
        clear.setObjectName("DangerButton")
        clear.clicked.connect(self.clear_history)
        row.addStretch(1)
        row.addWidget(clear)
        layout.addWidget(self.history_search)
        layout.addLayout(row)
        layout.addWidget(self.history_table, 1)
        return page

    def _logs_page(self) -> QWidget:
        """Build the logs page."""
        page, layout = self._page_shell("Logs", "Eventos y errores registrados por la aplicacion")
        self.logs_view.setReadOnly(True)
        self.logs_view.setObjectName("TextArea")
        row = QHBoxLayout()
        refresh = QPushButton("Actualizar logs")
        refresh.setObjectName("SecondaryButton")
        refresh.clicked.connect(self.render_logs)
        clear = QPushButton("Limpiar logs")
        clear.setObjectName("DangerButton")
        clear.clicked.connect(self.clear_logs)
        row.addStretch(1)
        row.addWidget(refresh)
        row.addWidget(clear)
        layout.addLayout(row)
        layout.addWidget(self.logs_view, 1)
        return page

    def _settings_page(self) -> QWidget:
        """Build the settings page."""
        page, layout = self._page_shell("Configuracion", "Controla el comportamiento de la aplicacion")
        panel = QFrame(objectName="Panel")
        form = QVBoxLayout(panel)
        settings = self.organizer.config.load()
        self.auto_check.setChecked(settings.auto_organize)
        self.startup_check.setChecked(startup.is_enabled() or settings.start_with_windows)
        self.startup_check.setEnabled(startup.is_supported())
        self.interval_spin.setRange(3, 300)
        self.interval_spin.setValue(settings.scan_interval_seconds)
        self.interval_spin.setSuffix(" seg")
        save = QPushButton("Guardar configuracion")
        save.setObjectName("PrimaryButton")
        save.clicked.connect(self.save_settings)
        form.addWidget(self.auto_check)
        form.addWidget(self.startup_check)
        form.addWidget(QLabel("Intervalo de escaneo automatico"))
        form.addWidget(self.interval_spin)
        form.addWidget(save)
        form.addStretch(1)
        layout.addWidget(panel, 1)
        return page

    def _themes_page(self) -> QWidget:
        """Build the theme page."""
        page, layout = self._page_shell("Temas", "Cambia rapidamente la apariencia")
        row = QHBoxLayout()
        dark = QPushButton("Dark Mode")
        dark.setObjectName("PrimaryButton")
        dark.clicked.connect(lambda: self.setStyleSheet(DARK_STYLESHEET))
        light = QPushButton("Light Mode")
        light.setObjectName("SecondaryButton")
        light.clicked.connect(lambda: self.setStyleSheet(LIGHT_STYLESHEET))
        row.addWidget(dark)
        row.addWidget(light)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)
        return page

    def _about_page(self) -> QWidget:
        """Build the about page."""
        page, layout = self._page_shell("Acerca de", "Proyecto profesional de organizador de archivos")
        about = QLabel(
            "Smart File Organizer clasifica archivos reales desde carpetas monitoreadas.\n\n"
            "Tecnologias: Python, PySide6, pathlib, shutil, JSON y logging.\n"
            "Hecho por Calva - Codigo fuente en GitHub"
        )
        about.setObjectName("PanelLabel")
        about.setWordWrap(True)
        layout.addWidget(about)
        layout.addStretch(1)
        return page

    def _add_stat_card(self, layout: QGridLayout, column: int, title: str, value: QLabel, subtitle: str) -> None:
        """Add a metric card to the dashboard."""
        card = QFrame(objectName="Panel")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 18, 22, 18)
        value.setObjectName("StatValue")
        card_layout.addWidget(value)
        card_layout.addWidget(QLabel(title))
        caption = QLabel(subtitle)
        caption.setObjectName("Success")
        card_layout.addWidget(caption)
        layout.addWidget(card, 0, column)

    def _build_activity_panel(self) -> QWidget:
        """Build the live activity list panel."""
        panel = QFrame(objectName="Panel")
        layout = QVBoxLayout(panel)
        layout.addWidget(QLabel("<b>Actividad del sistema</b>"))
        self.activity_list.setObjectName("List")
        layout.addWidget(self.activity_list, 1)
        return panel

    def _build_type_panel(self) -> QWidget:
        panel = QFrame(objectName="Panel")
        layout = QVBoxLayout(panel)

        layout.addWidget(QLabel("<b>Archivos por tipo</b>"))

        self.stats_type_list.setObjectName("List")
        layout.addWidget(self.stats_type_list)

        return panel

    def _build_folders_panel(self) -> QWidget:
        """Build the dashboard monitored folders panel."""
        panel = QFrame(objectName="Panel")
        layout = QVBoxLayout(panel)
        layout.addWidget(QLabel("<b>Carpetas monitoreadas activas</b>"))
        self.dashboard_folder_list.setObjectName("List")
        layout.addWidget(self.dashboard_folder_list, 1)
        open_hint = QLabel("Doble click para abrir una carpeta.")
        open_hint.setObjectName("Muted")
        layout.addWidget(open_hint)
        return panel

    def _build_folder_manager_panel(self) -> QWidget:
        """Build the full folder management panel."""
        panel = QFrame(objectName="Panel")
        layout = QVBoxLayout(panel)
        layout.addWidget(QLabel("<b>Carpetas monitoreadas activas</b>"))
        self.selected_folder_label.setObjectName("SelectedFolder")
        self.selected_folder_label.setWordWrap(True)
        layout.addWidget(self.selected_folder_label)
        self.folder_list.setObjectName("List")
        layout.addWidget(self.folder_list, 1)

        row = QHBoxLayout()
        self.folder_input.setPlaceholderText("Agregar carpeta del sistema...")
        add_button = QPushButton("+")
        add_button.setObjectName("PrimaryButton")
        add_button.clicked.connect(self.add_folder)
        browse_button = QPushButton("Buscar")
        browse_button.setObjectName("SecondaryButton")
        browse_button.clicked.connect(self.browse_folder)
        row.addWidget(self.folder_input, 1)
        row.addWidget(browse_button)
        row.addWidget(add_button)
        layout.addLayout(row)
        return panel

    def _build_file_locations_panel(self) -> QWidget:
        """Build the detected file locations panel."""
        panel = QFrame(objectName="Panel")
        layout = QVBoxLayout(panel)
        layout.addWidget(QLabel("<b>Ubicacion de archivos detectados</b>"))
        hint = QLabel("Archivo -> carpeta actual")
        hint.setObjectName("Muted")
        layout.addWidget(hint)
        self.file_locations_list.setObjectName("List")
        layout.addWidget(self.file_locations_list, 1)
        return panel

    def _build_stats_type_panel(self) -> QWidget:
        panel = QFrame(objectName="Panel")
        layout = QVBoxLayout(panel)

        layout.addWidget(QLabel("<b>Distribución por tipo</b>"))

        return panel

    def _build_stats_chart_panel(self) -> QWidget:
        panel = QFrame(objectName="Panel")
        layout = QVBoxLayout(panel)

        layout.addWidget(QLabel("<b>Actividad semanal</b>"))

        return panel

    def _build_extensions_panel(self) -> QWidget:
        """Build extension frequency panel."""
        panel = QFrame(objectName="Panel")
        layout = QVBoxLayout(panel)
        layout.addWidget(QLabel("<b>Extensiones mas comunes</b>"))
        self.extension_list.setObjectName("List")
        layout.addWidget(self.extension_list, 1)
        return panel

    def _build_largest_files_panel(self) -> QWidget:
        """Build largest files panel."""
        panel = QFrame(objectName="Panel")
        layout = QVBoxLayout(panel)
        layout.addWidget(QLabel("<b>Archivos mas pesados</b>"))
        self.largest_files_list.setObjectName("List")
        layout.addWidget(self.largest_files_list, 1)
        return panel

    def switch_page(self, index: int) -> None:
        """Switch main content page and update active navigation."""
        self.stack.setCurrentIndex(index)
        self.animate_page_transition()
        for button_index, button in enumerate(self.nav_buttons):
            button.setObjectName("NavActive" if button_index == index else "NavButton")
            button.style().unpolish(button)
            button.style().polish(button)
        if index == 4:
            self.render_history()
        elif index == 5:
            self.render_logs()

    def refresh(self) -> None:
        """Reload dashboard data from the current system folders."""
        self.snapshot = self.organizer.snapshot()
        if self.inventory is None:
            self.stat_total.setText("...")
            self.stat_size.setText("...")
        else:
            self.stat_total.setText(f"{self.inventory.total_files:,}")
            self.stat_size.setText(self.format_size(self.inventory.total_size_bytes))
        self.stat_today.setText(str(self.snapshot.organized_today))
        self.stat_folders.setText(str(len(self.snapshot.monitored_folders)))
        self.status_label.setText("Ultimo escaneo: ahora")
        self.stat_status.setText("Monitoreo activo" if self.monitoring_enabled else "Monitoreo detenido")
        self._render_activity(self.snapshot)
        self._render_file_locations(self.snapshot)
        self._render_folders(self.snapshot.monitored_folders)
        self.render_rules()
        self.render_history()
        self.render_logs()
        self.update_monitor_panel()

    def start_home_scan(self) -> None:
        """Start the recursive home inventory in a worker thread."""
        if self.inventory_thread is not None and self.inventory_thread.isRunning():
            return
        self.stat_total.setText("Analizando...")
        self.stat_size.setText("Analizando...")
        self.status_label.setText("Analizando /home en segundo plano...")
        self.inventory_thread = QThread(self)
        self.inventory_worker = HomeInventoryWorker(self.organizer)
        self.inventory_worker.moveToThread(self.inventory_thread)
        self.inventory_thread.started.connect(self.inventory_worker.run)
        self.inventory_worker.finished.connect(self.on_home_scan_finished)
        self.inventory_worker.failed.connect(self.on_home_scan_failed)
        self.inventory_worker.finished.connect(self.inventory_thread.quit)
        self.inventory_worker.failed.connect(self.inventory_thread.quit)
        self.inventory_worker.finished.connect(self.inventory_worker.deleteLater)
        self.inventory_thread.finished.connect(self.inventory_thread.deleteLater)
        self.inventory_thread.finished.connect(self.clear_inventory_thread)
        self.inventory_thread.start()

    def on_home_scan_finished(self, inventory: InventorySnapshot) -> None:
        """Receive home inventory results."""
        self.inventory = inventory
        most_common = inventory.files_by_type.most_common(1)
        self.stat_common.setText(most_common[0][0] if most_common else "None")
        self.status_label.setText(f"Analisis terminado: {inventory.root}")
        self.render_inventory_details(inventory)
        self.refresh()

    def on_home_scan_failed(self, message: str) -> None:
        """Handle inventory scan errors."""
        self.status_label.setText("No se pudo analizar /home")
        QMessageBox.warning(self, "Analisis incompleto", message)

    def clear_inventory_thread(self) -> None:
        """Clear worker references after a scan."""
        self.inventory_thread = None
        self.inventory_worker = None

    def animate_page_transition(self) -> None:
        """Fade the current page in for a smoother navigation feel."""
        effect = QGraphicsOpacityEffect(self.stack.currentWidget())
        self.stack.currentWidget().setGraphicsEffect(effect)
        self.fade_animation = QPropertyAnimation(effect, b"opacity", self)
        self.fade_animation.setDuration(180)
        self.fade_animation.setStartValue(0.35)
        self.fade_animation.setEndValue(1.0)
        self.fade_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.fade_animation.finished.connect(lambda: self.stack.currentWidget().setGraphicsEffect(None))
        self.fade_animation.start()

    def organize_now(self) -> None:
        """Organize files and refresh the dashboard."""
        moved = self._organize_safely(show_dialog=True)
        self.moved_this_session += len(moved)
        self.refresh()
        self._render_moved_files(moved)

    def monitor_tick(self) -> None:
        """Run one automatic monitor pass."""
        if not self.monitoring_enabled:
            return
        moved = self._organize_safely(show_dialog=False)
        self.moved_this_session += len(moved)
        self.refresh()
        if moved:
            self._render_moved_files(moved)

    def _organize_safely(self, show_dialog: bool) -> list[OrganizedFile]:
        """Run organization with UI error handling."""
        try:
            moved = self.organizer.organize_all()
        except OSError as error:
            QMessageBox.critical(self, "No se pudo organizar", str(error))
            return []
        if show_dialog:
            QMessageBox.information(self, "Organizacion completa", f"Se organizaron {len(moved)} archivos.")
        return moved

    def browse_folder(self) -> None:
        """Open a folder picker and fill the input."""
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta")
        if folder:
            self.folder_input.setText(folder)

    def add_folder(self) -> None:
        """Add a folder path from the input to monitored folders."""
        text = self.folder_input.text().strip()
        if not text:
            return
        path = Path(text)
        if not path.exists():
            QMessageBox.warning(self, "Carpeta no encontrada", "La carpeta indicada no existe.")
            return
        self.organizer.add_folder(path)
        self.folder_input.clear()
        self.refresh()

    def remove_selected_folder(self) -> None:
        """Remove selected monitored folder."""
        item = self.folder_list.currentItem()
        if item is None:
            QMessageBox.information(self, "Seleccion requerida", "Primero selecciona una carpeta monitoreada.")
            return
        path_text = item.data(Qt.ItemDataRole.UserRole)
        if not path_text:
            QMessageBox.information(self, "Seleccion requerida", "Selecciona una carpeta valida para eliminar.")
            return
        path = Path(str(path_text))
        confirmed = QMessageBox.question(
            self,
            "Eliminar carpeta monitoreada",
            f"Vas a eliminar esta carpeta del monitoreo:\n\n{path}\n\nLos archivos no se borran. Solo deja de monitorearse.",
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        self.organizer.remove_folder(path)
        self.refresh()

    def remove_all_folders(self) -> None:
        """Remove all monitored folders after confirmation."""
        folders = self.snapshot.monitored_folders
        if not folders:
            QMessageBox.information(self, "Sin carpetas", "No hay carpetas monitoreadas para eliminar.")
            return
        folder_list = "\n".join(str(folder) for folder in folders)
        confirmed = QMessageBox.question(
            self,
            "Eliminar todas las carpetas",
            f"Vas a eliminar todas estas carpetas del monitoreo:\n\n{folder_list}\n\nLos archivos no se borran.",
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        self.organizer.remove_all_folders()
        self.refresh()

    def open_current_folder(self) -> None:
        """Open the currently selected folder."""
        item = self.folder_list.currentItem()
        if item is not None:
            self.open_selected_folder(item)

    def open_selected_folder(self, item: QListWidgetItem) -> None:
        """Open a monitored folder in the system file explorer."""
        path_text = item.data(Qt.ItemDataRole.UserRole) or item.text()
        path = Path(str(path_text))
        if path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def update_selected_folder_label(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        """Show which monitored folder is currently selected."""
        del previous
        if current is None or not current.data(Qt.ItemDataRole.UserRole):
            self.selected_folder_label.setText("Selecciona una carpeta para eliminarla.")
            return
        self.selected_folder_label.setText(
            f"Seleccionada para eliminar del monitoreo: {current.data(Qt.ItemDataRole.UserRole)}"
        )

    def toggle_monitoring(self) -> None:
        """Start or stop automatic organization."""
        self.monitoring_enabled = not self.monitoring_enabled
        self.apply_timer_settings()
        self.update_monitor_panel()
        self.refresh()

    def save_settings(self) -> None:
        """Persist settings from the configuration page."""
        self.monitoring_enabled = self.auto_check.isChecked()
        if self.startup_check.isChecked():
            startup.enable()
        else:
            startup.disable()
        self.organizer.save_settings(
            auto_organize=self.auto_check.isChecked(),
            scan_interval_seconds=self.interval_spin.value(),
            start_with_windows=self.startup_check.isChecked(),
        )
        self.apply_timer_settings()
        self.refresh()
        QMessageBox.information(self, "Configuracion guardada", "Los cambios fueron guardados.")

    def setup_tray_icon(self) -> None:
        """Create a tray icon so background mode can be restored without a console."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray_icon = QSystemTrayIcon(self)
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        self.tray_icon.setIcon(icon)
        self.tray_icon.setToolTip("Smart File Organizer")

        menu = QMenu()
        show_action = menu.addAction("Abrir Smart File Organizer")
        show_action.triggered.connect(self.show_from_tray)
        organize_action = menu.addAction("Organizar ahora")
        organize_action.triggered.connect(self.organize_now)
        menu.addSeparator()
        quit_action = menu.addAction("Salir")
        quit_action.triggered.connect(QApplication.instance().quit)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()

    def start_background_mode(self) -> None:
        """Start minimized/hidden when launched by Windows startup."""
        self.monitoring_enabled = True
        self.auto_check.setChecked(True)
        self.apply_timer_settings()
        self.hide()
        if self.tray_icon is not None:
            self.tray_icon.showMessage(
                "Smart File Organizer",
                "La app se inicio en segundo plano.",
                QSystemTrayIcon.MessageIcon.Information,
                2500,
            )

    def show_from_tray(self) -> None:
        """Restore the main window from the tray."""
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Restore the window when the tray icon is clicked."""
        if reason in {QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick}:
            self.show_from_tray()

    def closeEvent(self, event: object) -> None:
        """Hide to tray instead of closing when tray mode is available."""
        if self.tray_icon is not None and self.tray_icon.isVisible():
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "Smart File Organizer",
                "La app sigue funcionando en segundo plano.",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )
            return
        super().closeEvent(event)

    def apply_timer_settings(self) -> None:
        """Apply timer interval and active state."""
        settings = self.organizer.config.load()
        self.timer.setInterval(settings.scan_interval_seconds * 1000)
        if self.monitoring_enabled:
            self.timer.start()
        else:
            self.timer.stop()

    def update_monitor_panel(self) -> None:
        """Update sidebar monitor controls."""
        self.monitor_title.setText("<b>Monitoreo Activo</b>" if self.monitoring_enabled else "<b>Monitoreo Detenido</b>")
        self.monitor_description.setText(
            "Organizacion automatica encendida."
            if self.monitoring_enabled
            else "Usa Organizar ahora o inicia el monitoreo."
        )
        self.monitor_button.setText("Detener" if self.monitoring_enabled else "Iniciar")
        self.monitor_button.setObjectName("DangerButton" if self.monitoring_enabled else "PrimaryButton")
        self.monitor_button.style().unpolish(self.monitor_button)
        self.monitor_button.style().polish(self.monitor_button)

    def render_rules(self) -> None:
        """Render extension rules."""
        self.rules_table.setRowCount(0)
        for row, (category, extensions) in enumerate(CATEGORY_EXTENSIONS.items()):
            self.rules_table.insertRow(row)
            self.rules_table.setItem(row, 0, QTableWidgetItem(category))
            self.rules_table.setItem(row, 1, QTableWidgetItem(", ".join(sorted(extensions))))

    def render_history(self) -> None:
        """Render persisted history with optional search filter."""
        query = self.history_search.text().lower().strip()
        items = self.organizer.history()
        if query:
            items = [item for item in items if query in " ".join(item.values()).lower()]
        self.history_table.setRowCount(0)
        for row, item in enumerate(items[:250]):
            self.history_table.insertRow(row)
            values = [
                item.get("date", ""),
                item.get("name", ""),
                item.get("category", ""),
                item.get("source", ""),
                item.get("destination", ""),
            ]
            for column, value in enumerate(values):
                self.history_table.setItem(row, column, QTableWidgetItem(value))

    def render_logs(self) -> None:
        """Render log text."""
        self.logs_view.setPlainText(self.organizer.logs())

    def clear_history(self) -> None:
        """Clear move history after confirmation."""
        confirmed = QMessageBox.question(
            self,
            "Limpiar historial",
            "Quieres borrar el historial de archivos organizados?",
        )
        if confirmed == QMessageBox.Yes:
            self.organizer.clear_history()
            self.refresh()

    def clear_logs(self) -> None:
        """Clear logs after confirmation."""
        confirmed = QMessageBox.question(self, "Limpiar logs", "Quieres borrar el archivo de logs?")
        if confirmed == QMessageBox.Yes:
            self.organizer.clear_logs()
            self.render_logs()

    def render_inventory_details(self, inventory: InventorySnapshot) -> None:
        """Render recursive home inventory details."""
        self.extension_list.clear()
        self.inventory_meta_label.setText(
            f"Raiz: {inventory.root} | Omitidos: {inventory.skipped_paths} | Peso: {self.format_size(inventory.total_size_bytes)}"
        )
        for extension, count in inventory.files_by_extension.most_common(12):
            self.extension_list.addItem(f"{extension}: {count:,}")

        self.largest_files_list.clear()
        for path, size in inventory.largest_files:
            self.largest_files_list.addItem(f"{self.format_size(size)}  {path}")

    def _render_activity(self, snapshot: DashboardSnapshot) -> None:
        """Render current source files in the activity list."""
        self.activity_list.clear()
        for path in snapshot.latest_files:
            category = self.organizer.category_for(path)
            self.activity_list.addItem(f"{path.name}  ->  {category}  |  {path.parent}")
        if not snapshot.latest_files:
            self.activity_list.addItem("No hay archivos pendientes en las carpetas monitoreadas.")

    def _render_file_locations(self, snapshot: DashboardSnapshot) -> None:
        """Render where each pending file is currently located."""
        self.file_locations_list.clear()
        for path in snapshot.pending_files:
            category = self.organizer.category_for(path)
            self.file_locations_list.addItem(f"{path.name}  ->  {category}  |  Carpeta: {path.parent}")
        if not snapshot.pending_files:
            self.file_locations_list.addItem("No hay archivos pendientes para mostrar ubicaciones.")

    def _render_moved_files(self, moved: list[OrganizedFile]) -> None:
        """Render files moved in the current operation."""
        self.activity_list.clear()
        if not moved:
            self.activity_list.addItem("No habia archivos nuevos para organizar.")
            return
        for item in moved[:12]:
            self.activity_list.addItem(f"{item.name}  ->  {item.category}  |  {item.source.parent}")

    def _render_folders(self, folders: list[Path]) -> None:
        """Render monitored system folders."""
        self.dashboard_folder_list.clear()
        self.folder_list.clear()
        for folder in folders:
            dashboard_item = QListWidgetItem(str(folder))
            dashboard_item.setData(Qt.ItemDataRole.UserRole, str(folder))
            manager_item = QListWidgetItem(str(folder))
            manager_item.setData(Qt.ItemDataRole.UserRole, str(folder))
            self.dashboard_folder_list.addItem(dashboard_item)
            self.folder_list.addItem(manager_item)
        if not folders:
            self.dashboard_folder_list.addItem("No se encontraron carpetas por defecto.")
            self.folder_list.addItem("No se encontraron carpetas por defecto. Agrega una manualmente.")
        self.update_selected_folder_label(self.folder_list.currentItem(), None)

    def _render_types(self, files_by_type: Counter[str]) -> None:
        self.stats_type_list.clear()

        total = sum(files_by_type.values()) or 1

        if not files_by_type:
            self.stats_type_list.addItem("Sin archivos pendientes.")
            return

        for category, count in files_by_type.most_common():
            percent = round((count / total) * 100)
            self.stats_type_list.addItem(
                f"{category}: {count} archivos ({percent}%)"
            )
    def format_size(self, size: int) -> str:
        """Format bytes as a compact human-readable value."""
        value = float(size)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if value < 1024 or unit == "TB":
                return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
            value /= 1024
        return f"{size} B"


class HomeInventoryWorker(QObject):
    """Worker object that scans the user's home directory off the UI thread."""

    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, organizer: FileOrganizer) -> None:
        """Create the worker."""
        super().__init__()
        self.organizer = organizer

    def run(self) -> None:
        """Run the inventory scan."""
        try:
            self.finished.emit(self.organizer.home_inventory())
        except OSError as error:
            self.failed.emit(str(error))


DARK_STYLESHEET = """
QWidget#Page {
    background: #0b1420;
    color: #f4f7fb;
    font-family: Segoe UI;
}
QFrame#Sidebar {
    background: #101b29;
    border-right: 1px solid #243347;
}
QFrame#Panel {
    background: #111d2b;
    border: 1px solid #243347;
    border-radius: 8px;
}
QLabel {
    color: #f4f7fb;
}
QLabel#Brand {
    font-size: 16px;
}
QLabel#Brand span,
QLabel#Muted {
    color: #93a4ba;
}
QLabel#PageTitle h1 {
    font-size: 26px;
}
QLabel#PageTitle span {
    color: #bcc8d8;
}
QLabel#StatValue {
    font-size: 30px;
    font-weight: 700;
}
QLabel#Success {
    color: #55f06a;
}
QLabel#SelectedFolder {
    color: #55f06a;
    background: #142236;
    border: 1px solid #243347;
    border-radius: 7px;
    padding: 10px;
}
QPushButton {
    border: none;
    border-radius: 7px;
    padding: 10px 14px;
    color: #ffffff;
    background: #142033;
    font-weight: 600;
}
QPushButton#PrimaryButton {
    background: #4c68ff;
}
QPushButton#SecondaryButton {
    background: #121e2f;
    border: 1px solid #243347;
}
QPushButton#DangerButton {
    background: #c72d44;
}
QPushButton#NavActive {
    background: #4c68ff;
    text-align: left;
}
QPushButton#NavButton {
    background: transparent;
    text-align: left;
}
QListWidget,
QTableWidget,
QTextEdit {
    background: transparent;
    border: none;
    color: #f4f7fb;
    outline: 0;
}
QHeaderView::section {
    background: #142236;
    color: #f4f7fb;
    border: none;
    padding: 8px;
}
QListWidget::item,
QTableWidget::item {
    padding: 8px;
    border-bottom: 1px solid #1d2a3a;
}
QLineEdit,
QSpinBox {
    background: #132033;
    border: 1px solid #243347;
    border-radius: 7px;
    color: #f4f7fb;
    padding: 10px;
}
QCheckBox {
    color: #f4f7fb;
}
"""


LIGHT_STYLESHEET = """
QWidget#Page {
    background: #f4f7fb;
    color: #172033;
    font-family: Segoe UI;
}
QFrame#Sidebar {
    background: #e8edf5;
    border-right: 1px solid #c9d4e2;
}
QFrame#Panel {
    background: #ffffff;
    border: 1px solid #d7dfeb;
    border-radius: 8px;
}
QLabel {
    color: #172033;
}
QLabel#Brand span,
QLabel#Muted {
    color: #64748b;
}
QLabel#StatValue {
    font-size: 30px;
    font-weight: 700;
}
QLabel#Success {
    color: #16803a;
}
QLabel#SelectedFolder {
    color: #16803a;
    background: #ffffff;
    border: 1px solid #c9d4e2;
    border-radius: 7px;
    padding: 10px;
}
QPushButton {
    border: none;
    border-radius: 7px;
    padding: 10px 14px;
    color: #172033;
    background: #dce6f3;
    font-weight: 600;
}
QPushButton#PrimaryButton,
QPushButton#NavActive {
    background: #4c68ff;
    color: #ffffff;
}
QPushButton#DangerButton {
    background: #c72d44;
    color: #ffffff;
}
QPushButton#NavButton {
    background: transparent;
    text-align: left;
}
QListWidget,
QTableWidget,
QTextEdit {
    background: transparent;
    border: none;
    color: #172033;
    outline: 0;
}
QHeaderView::section {
    background: #e8edf5;
    color: #172033;
    border: none;
    padding: 8px;
}
QLineEdit,
QSpinBox {
    background: #ffffff;
    border: 1px solid #c9d4e2;
    border-radius: 7px;
    color: #172033;
    padding: 10px;
}
QCheckBox {
    color: #172033;
}
"""
