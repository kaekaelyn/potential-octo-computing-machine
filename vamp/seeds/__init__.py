"""Seed data loading (CLAUDE.md: "Seed data = YAML in seeds/, imported
idempotently"). The researched OKC-metro datasets live as editable YAML +
markdown in the repo's top-level ``seeds/`` directory; this package imports
them into SQLite on startup, never overwriting rows a human has since edited.
"""
