# Design notes

These documents are the *rationale* behind the implementation in `whisperbar/`
and `Whisperbar.spoon/` — the pipeline stage by stage, the correction argument,
the injection problem, and every failure mode hit in production.

They were written before the code was packaged as a product, so they describe
the design in general terms and occasionally name a module that has since been
renamed. The reasoning is current; the file names may not be.

Start with **`05-gotchas.md`**. It is the one that saves time.
