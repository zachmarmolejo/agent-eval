# results

`make eval` always writes:

- `latest.md` — human table
- `latest.json` — same metrics
- `latest-traces.jsonl` — final answers and tool calls
- `<date>-<model>/` — dated copy of those three files

Live model runs stay in this folder and are gitignored. [`examples/fake/`](examples/fake/report.md) is the committed snapshot of a clean fake run so a clone can diff `make eval` without overwriting the example.

If the printed table and a traces file disagree, the traces win until you explain why.
