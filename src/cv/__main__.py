"""Allow running the CV pipeline as a module: python -m src.cv analyze <video>"""
from src.cv.cli import main
raise SystemExit(main())
