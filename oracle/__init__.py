"""Independent oracle for the Brewbird golden questions.

Computes expected answers straight from the raw data pack with pandas, following
docs/definitions.md. It must never import from the pipeline (src/); a test enforces this.
"""
