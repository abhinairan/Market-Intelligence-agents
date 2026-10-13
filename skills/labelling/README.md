# Labelling skill

The prompts the pipeline's label model runs on. They are kept here, apart from the code
and apart from the client config, so each can change without the others.

| File | Used for | Filled in from |
|---|---|---|
| `sentiment.md` | One call per distinct text: positive, neutral or negative | `sentiment.rules` in `config/<client>/labels.yaml` |
| `complaint_codes.md` | One call per negative text about the client: its complaint codes | the client's complaint taxonomy file, quoted verbatim, and `codes.rules` in `labels.yaml` |

`{{name}}` marks a slot the pipeline fills (`src/halyard/ingest/labelling.py`). The filled
prompt is hashed into the label cache key, so editing a prompt, a rule or the taxonomy
relabels exactly the texts that prompt covers and nothing else. See PLAN §5a and D-35.

The text being labelled is never placed in these prompts. It is sent separately, as data.
