"""
dictation — a fully-local speech-to-text dictation pipeline.

    from dictation.transcribe import transcribe
    from dictation.correct import correct

    text, lang = transcribe(Path("take.wav"))
    final, meta = correct(text, lang)

No network call anywhere in this package.
"""

__version__ = "0.1.0"
