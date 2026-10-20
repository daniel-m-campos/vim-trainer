# Ingest log

One section per `vimtrainer-content ingest` run.

## 2026-10-20

1 records from `6.md`: 1 sequences to verify, 0 wording flags, 1 exercises updated, 0 divergences

- `py/m.find/d14d324bb9` `fTcwFalse<Esc>` (10 keys, par 11): new canonical; `f=lcwFalse<Esc>` -> alternates; idiom `fTcw{{text}}<Esc>` -> idioms_learned.toml

## 2026-10-20

1 records from `7.md`: 1 sequences to verify, 0 wording flags, 1 exercises updated, 0 divergences

- `py/m.find/1d686fca5d` `f1cw100<Esc>` (8 keys, par 10): new canonical; `2f=lcw100<Esc>` -> alternates; idiom `f1cw{{text}}<Esc>` -> idioms_learned.toml

Follow-up: both sequences use the same idiom, find the first character of the old value. The
`change_kwarg_value` m.find template now lists `f{old[0]}` with every change motion as a canonical
variant, so the rebuild re-pars every sibling; the two literal learned idioms were removed.
