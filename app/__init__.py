"""Supplier quote extraction pipeline.

One module per pipeline stage so the model/code boundary is literal:

    loader -> extractor -> validate -> normalize -> review -> writer

Only `extractor` touches the LLM. Everything downstream is deterministic and
unit-testable.
"""
