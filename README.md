# Huawei Cup 2026 workspace (paper PDFs excluded)

This private repository contains the browsable source and documentation export of `/Users/futaoran/Desktop/华为杯2026` as of 2026-09-27.

Paper PDFs are intentionally excluded. The complete non-PDF workspace is stored in the private GitHub Release assets for tag `2026-09-27-no-paper-pdf`, as six 1-GiB tar.gz parts. Reconstruct and extract with:

```bash
cat huawei-cup-2026-no-paper-pdf.tar.gz.part* > huawei-cup-2026-no-paper-pdf.tar.gz
tar -xzf huawei-cup-2026-no-paper-pdf.tar.gz
```

`file-manifest.jsonl.gz` records source SHA-256 values. `excluded-files.json` records every excluded PDF, including PDFs found inside ZIP archives; 16 ZIP archives were rewritten to remove embedded paper PDFs before packaging. Generated build artefacts, virtual environments, and Git metadata are preserved in the full archive only when they were part of the source and were not PDFs.
