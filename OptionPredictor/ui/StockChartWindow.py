import sys
import subprocess
import webview
import tkinter as tk
from tkinter import messagebox

class StockChartWindow:
    """
    A class to display a TradingView chart in a completely separate Python process
    using pywebview, so it never interferes with the main Tkinter window.
    """
    def __init__(self, parent, ticker, theme="light"):
        """
        Args:
            parent: The main tkinter window (used only for error dialogs).
            ticker (str): Stock ticker symbol (e.g., "AAPL").
            theme (str): "light" or "dark".
        """
        self.parent = parent
        self.ticker = ticker.upper()
        self.theme = "dark" if theme == "dark" else "light"
        self.title = f"TradingView Chart: {self.ticker}"

        # Build TradingView widget URL
        self.url = (
            f"https://s.tradingview.com/widgetembed/"
            f"?frameElementId=tradingview_chart"
            f"&symbol={self.ticker}"
            f"&interval=D"
            f"&symboledit=1"
            f"&saveimage=1"
            f"&toolbarbg=f1f3f6"
            f"&studies=[]"
            f"&theme={self.theme}"
            f"&style=1"
            f"&timezone=Etc/UTC"
            f"&withdateranges=1"
            f"&hide_side_toolbar=0"
            f"&allow_symbol_change=1"
            f"&enable_publishing=0"
            f"&calendar=1"
            f"&hotlist=1"
            f"&news=1"
            f"&details=1"
            f"&show_popup_button=1"
            f"&autosize=1"
        )

        self._launch_chart_process()

    def _launch_chart_process(self):
        """
        Spawn a separate Python process that runs pywebview on its own main thread.
        """
        try:
            cmd = [
                sys.executable,
                "-c",
                (
                    "import webview;"
                    f"webview.create_window({repr(self.title)},{repr(self.url)},"
                    "width=1000,height=750,resizable=True,confirm_close=False);"
                    "webview.start()"
                )
            ]
            subprocess.Popen(cmd)
        except Exception as e:
            messagebox.showerror(
                "Chart Load Error",
                f"Failed to launch TradingView chart:\n{e}",
                parent=self.parent
            )
