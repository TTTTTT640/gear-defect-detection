"""
统计图表 + 检测历史组件
基于matplotlib嵌入Qt实现(避免依赖QtChart)
"""

import time
from datetime import datetime
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
                             QTableWidgetItem, QHeaderView, QLabel)
from PyQt5.QtCore import Qt

try:
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("[图表] matplotlib未安装，图表功能不可用。pip install matplotlib")


class StatsChartWidget(QWidget):
    """实时检测统计图表 — 饼图(合格率) + 柱状图(各类别计数)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)

        if not HAS_MATPLOTLIB:
            layout.addWidget(QLabel("图表需要matplotlib: pip install matplotlib"))
            return

        self.figure = Figure(figsize=(5, 2.5), dpi=80)
        self.figure.set_facecolor("#f8f9fa")
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)

        self._init_empty()

    def _init_empty(self):
        """初始化空图表"""
        if not HAS_MATPLOTLIB:
            return
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.text(0.5, 0.5, "等待检测数据...", ha="center", va="center",
                fontsize=12, color="#95a5a6", fontfamily="SimHei")
        ax.axis("off")
        self.canvas.draw()

    def update_chart(self, stats):
        """更新图表

        Args:
            stats: dict from DetectionLogger.get_stats()
                   {total, good, well, bad, miss, defect_rate, pass_rate}
        """
        if not HAS_MATPLOTLIB:
            return
        if stats["total"] == 0:
            self._init_empty()
            return

        self.figure.clear()

        # 左: 饼图
        ax1 = self.figure.add_subplot(121)
        passed = stats.get("good", 0) + stats.get("well", 0)
        defects = stats.get("bad", 0) + stats.get("miss", 0)
        if passed + defects > 0:
            sizes = [passed, defects]
            labels = [f"合格\n{passed}", f"缺陷\n{defects}"]
            colors = ["#2ecc71", "#e74c3c"]
            explode = (0, 0.05)
            ax1.pie(sizes, labels=labels, colors=colors, explode=explode,
                    autopct="%1.1f%%", startangle=90,
                    textprops={"fontfamily": "SimHei", "fontsize": 9})
        ax1.set_title(f"合格率 (共{stats['total']}件)",
                      fontfamily="SimHei", fontsize=10, fontweight="bold")

        # 右: 柱状图
        ax2 = self.figure.add_subplot(122)
        categories = ["good", "well", "bad", "miss"]
        labels_cn = ["齿轮\n完好", "分类\n合格", "表面\n缺陷", "缺齿"]
        values = [stats.get(c, 0) for c in categories]
        colors = ["#27ae60", "#2ecc71", "#e74c3c", "#e67e22"]
        bars = ax2.bar(labels_cn, values, color=colors, edgecolor="white", linewidth=0.5)
        for bar, v in zip(bars, values):
            if v > 0:
                ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
                         str(v), ha="center", va="bottom", fontsize=9, fontweight="bold")
        ax2.set_title("检测分布", fontfamily="SimHei", fontsize=10, fontweight="bold")
        ax2.tick_params(axis="x", labelsize=8)
        ax2.set_ylabel("数量", fontfamily="SimHei", fontsize=9)

        self.figure.tight_layout()
        self.canvas.draw()


class DetectionHistoryWidget(QWidget):
    """检测历史记录表"""

    MAX_ROWS = 200  # 最多显示200条

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)

        header = QLabel("检测历史")
        header.setStyleSheet("font-weight: bold; font-size: 13px; color: #2c3e50; padding: 3px;")
        layout.addWidget(header)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["时间", "阶段", "类别", "置信度", "动作"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
            QTableWidget {
                font-size: 12px; border: 1px solid #bdc3c7;
                gridline-color: #ecf0f1;
            }
            QTableWidget::item { padding: 3px; }
            QHeaderView::section {
                background-color: #2c3e50; color: white;
                font-weight: bold; padding: 4px; border: none;
            }
        """)
        layout.addWidget(self.table)

    def add_record(self, class_name, confidence, action, stage=0):
        """添加一条检测记录

        Args:
            class_name: 检测类别
            confidence: 置信度
            action: 执行动作描述
            stage: 检测阶段
        """
        row = 0  # 插入到最上方
        self.table.insertRow(row)

        ts = datetime.now().strftime("%H:%M:%S")
        items = [
            ts,
            f"阶段{stage}",
            class_name,
            f"{confidence:.1%}",
            action,
        ]

        # 根据类别设置行颜色
        color_map = {
            "good": "#d5f5e3",
            "well": "#d5f5e3",
            "bad": "#fadbd8",
            "miss": "#fdebd0",
        }
        bg = color_map.get(class_name, "#ffffff")

        for col, text in enumerate(items):
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignCenter)
            item.setBackground(Qt.GlobalColor.white)  # reset
            self.table.setItem(row, col, item)

        # 设置行背景色
        for col in range(5):
            item = self.table.item(row, col)
            if item:
                from PyQt5.QtGui import QColor
                item.setBackground(QColor(bg))

        # 限制行数
        while self.table.rowCount() > self.MAX_ROWS:
            self.table.removeRow(self.table.rowCount() - 1)

    def clear(self):
        self.table.setRowCount(0)
