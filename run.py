#!/usr/bin/env python
"""실행 진입점.

src/ 패키지를 경로에 올리고 CLI를 실행한다.
예) ./venv/bin/python run.py data/input/sample_request.csv --client 가상도서관 --discount 0.10
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from aladin_automation.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
