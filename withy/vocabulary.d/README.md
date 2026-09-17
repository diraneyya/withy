# Shipped vocabulary

Terms that travel with the code rather than living in each user's
`~/.config/withy/vocabulary.txt`. This is where a **downstream fork** puts its
organisation's internal tool names, product names and jargon — the words speech
recognition will never get right and that every employee would otherwise have to
type into their own config by hand.

**Add a new file; never edit someone else's.** A fork that edits a shared file
collides with upstream on it at every `git pull`. `acme.txt` next to `withy.txt`
never conflicts. Only `*.txt` is read — this README is not.

## Format

Whitespace- or newline-separated terms; `#` starts a comment. Two optional
section headings decide how each term is handled:

```
# needs the sentence around it to be judged safely (this is the default)
[context]
Seafile  Handy

# no English collision — correct by exact match, no model required
[deterministic]
Kubernetes  Grafana  Forgejo  PagerDuty
```

**Default to `[context]`.** Put a term under `[deterministic]` only when the
words that produce it could not plausibly be anything else. "Forge Joe" is
nobody's sentence, so `Forgejo` is safe. "C file" is a real thing a programmer
says, so `Seafile` is not — it needs the model to read the sentence.

A wrong `[deterministic]` entry corrupts speech silently; a wrong `[context]`
entry merely fails to help. That asymmetry is why the default is the safe one.

## Keep it short

Every term is a chance to correct a word and a chance to corrupt one. An
auto-derived index of a few thousand terms, measured against 360 real
dictations, made the text **worse 63% of the time it fired**. Tens of terms is a
safe collision surface. Thousands is not.

Check what is actually in effect, and where each term came from, with:

    withy vocab
