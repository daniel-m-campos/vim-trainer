"""Differential testing of the browser emulator against Neovim.

- ``generate``: seeded key sequences over the drilled command set, and the buffers they run on.
- ``compare``: normalise both sides to a ``Side``, diff them, classify and render findings.
- ``shrink``: minimise a diverging sequence.
- ``web`` / ``run``: the Node worker driver and the ``difftest`` CLI subcommand.
"""
