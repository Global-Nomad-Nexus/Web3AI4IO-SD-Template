# Public-input reproduction

Both executions started from fresh work directories, downloaded the immutable raw archive anonymously, verified its SHA-256, and rebuilt the full pipeline. No precomputed Parquet tables were used as reconstructed outputs.

| Run | Result | Actual elapsed time | Runtime |
|---|---|---|---|
| Local notebook | 14/14 code cells; PASS | 1062.525 seconds | 3.12.14 (main, Aug 25 2026, 13:50:33) [Clang 22.1.3 ] |
| Hosted Google Colab | 14/14 code cells; PASS | 2938.166 seconds | 3.13.15 (main, Aug  6 2026, 11:06:22) [GCC 13.3.0] |

Each run matched all 3,491 raw files and all 16 semantic tables against the frozen manifest. The two runs also agree with each other. Thresholds 1 and 3 were actually reapplied and defaults restored, with raw/base hashes unchanged.

- [Local receipt](../reports/public_reproduction.local.json)
- [Local notebook execution](../reports/local_public_verification.json)
- [Colab active-shell receipt](../reports/colab.json)
- [Colab reconstruction receipt](../reports/public_reproduction.colab.json)
- [Executed Colab notebook](../../../notebooks/01_On_Chain_Tutorial.executed.ipynb)
- [Editable Drive notebook](https://colab.research.google.com/drive/1c1_GtrxFXzwXa988ptNuvOUsnqZ6hGs-), saved in the requested shared folder; teacher edit access observed in Chrome.

Code commit: `7bb0c2ad5f8e3336338cd0e9265074015a7b4c35`. Data revision: `8b29598a6565b67a8a943962dbf77f3d6b2559de`. Notebook source SHA-256: `b784ad6c7eddb640c1718f81ea49a827b42b3f5ef8b9031ebdaf464aa694f275`. The separately named original baseline reports remain historical evidence; their seven-cell notebook execution is not this 14-cell run.

This is software reproduction, not independent coauthor review. Shilin's real tutorial, reciprocal coauthor reproduction and joint integration remain pending. Source/decoding/state limitations in the tutorial remain applicable. No email was sent and the PR was not merged.
