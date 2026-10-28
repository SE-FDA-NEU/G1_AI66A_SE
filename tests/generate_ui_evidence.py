"""Generate responsive screenshot evidence for core screens (US22, #114).

Uses headless Chrome to render core marketplace screens at desktop (1280px)
and mobile (390px) viewports, verifying layout integrity, button contrast,
and input sizing.
"""

import os
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "docs" / "images" / "responsive"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
if not Path(CHROME_PATH).exists():
    CHROME_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


def capture_screenshot(url: str, output_path: Path, width: int, height: int) -> bool:
    """Capture a screenshot of a URL at specific viewport dimensions."""
    cmd = [
        CHROME_PATH,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        f"--window-size={width},{height}",
        "--virtual-time-budget=2500",
        f"--screenshot={output_path}",
        url,
    ]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return res.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0


def main() -> int:
    port = "8142"
    base_url = f"http://127.0.0.1:{port}"
    server_log = Path(tempfile.gettempdir()) / "ui-styling-server.log"

    with tempfile.TemporaryDirectory(prefix="ui-evidence-") as tmpdir:
        db_path = Path(tmpdir) / "evidence.db"
        env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}", "DEBUG": "false"}

        # Initialize schema and seed demo data
        subprocess.run([sys.executable, "-m", "src.database"], cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)
        subprocess.run([sys.executable, "-m", "src.seed", "--demo"], cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)

        windows = os.name == "nt"
        with open(server_log, "w", encoding="utf-8") as log:
            server = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "src.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    port,
                ],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if windows else 0,
            )

        try:
            # Wait for server
            for _ in range(50):
                try:
                    with urllib.request.urlopen(f"{base_url}/health", timeout=1) as resp:
                        if resp.status == 200:
                            break
                except Exception:
                    time.sleep(0.1)
            else:
                print("Server failed to start")
                return 1

            screens = [
                ("desktop-catalog.png", f"{base_url}/products", 1280, 800),
                ("mobile-catalog.png", f"{base_url}/products", 390, 844),
                ("desktop-cart-empty.png", f"{base_url}/cart", 1280, 800),
                ("mobile-cart-empty.png", f"{base_url}/cart", 390, 844),
                ("desktop-checkout.png", f"{base_url}/checkout", 1280, 800),
                ("mobile-checkout.png", f"{base_url}/checkout", 390, 844),
                ("desktop-login.png", f"{base_url}/login", 1280, 800),
                ("mobile-login.png", f"{base_url}/login", 390, 844),
            ]

            print(f"Capturing {len(screens)} responsive screenshots using Chrome...")
            success_count = 0
            for filename, url, w, h in screens:
                out = OUTPUT_DIR / filename
                ok = capture_screenshot(url, out, w, h)
                if ok:
                    print(f"  [OK] {filename} ({w}x{h}) - {out.stat().st_size} bytes")
                    success_count += 1
                else:
                    print(f"  [FAILED] {filename} ({w}x{h})")

            print(f"Successfully captured {success_count}/{len(screens)} screenshots in {OUTPUT_DIR}")
            return 0 if success_count == len(screens) else 1

        finally:
            if windows:
                server.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                server.terminate()
            try:
                server.wait(timeout=5)
            except Exception:
                server.kill()


if __name__ == "__main__":
    sys.exit(main())
