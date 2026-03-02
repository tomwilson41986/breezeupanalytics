"""Allow running training tools as a module: python -m src.cv.training <command>"""
from src.cv.training.cli import main
raise SystemExit(main())
