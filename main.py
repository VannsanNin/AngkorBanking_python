from pathlib import Path
import sys
import os

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Silence noisy Qt font fallback warnings such as:
# "OpenType support missing for ... script 32"
existing_rules = os.environ.get("QT_LOGGING_RULES", "").strip()
font_warning_rules = "qt.qpa.fonts.warning=false;qt.text.font.db.warning=false"
if font_warning_rules not in existing_rules:
    os.environ["QT_LOGGING_RULES"] = (
        f"{existing_rules};{font_warning_rules}".strip(";")
        if existing_rules
        else font_warning_rules
    )

from angkor_banking.app import main


if __name__ == "__main__":
    main()
