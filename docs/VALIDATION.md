# Validation notes

This document records what the archived local validation artifacts support and, equally importantly, what they do not support.

## Recorded integration snapshot

The May 2026 dashboard validation artifact contained 29 passing checks covering backend/frontend availability, model loading, market/news provenance, recommendation output, paper-execution traceability, portfolio-provider state, and screenshot inventory.

Selected recorded values:

| Item | Recorded result |
| --- | --- |
| Supported assets | 12 |
| Market provenance | 3 live, 6 delayed, 3 fallback, 0 unknown |
| Historical points checked | 100 for AAPL and 100 for EUR/USD |
| News items in snapshot | 15 live-labeled items |
| Recommendations in snapshot | 20 |
| Recent Alpaca Paper orders checked | 50 |
| Audit result | PASS in the archived local environment |

The public portfolio edition intentionally excludes credential audits, account/order identifiers, raw broker artifacts, private uploads, large datasets, the defense video, and the presentation deck.

## Model interpretation

| Model path | Recorded result | Use in the prototype |
| --- | --- | --- |
| Binary XGBoost | 51.67% accuracy | Retained only as a weak input combined with other signals |
| Three-class XGBoost | 47.90% accuracy; below majority baseline | Excluded from final recommendation fusion |
| LSTM | Planned extension in the archived status | Not used in the final recommendation path |
| FinBERT | Implemented as an optional path | Disabled in the archived local run; heuristic NLP used by default |

These results do not establish profitability or production readiness. A stronger evaluation would require a fixed out-of-sample protocol, leakage checks, class-balanced metrics, transaction-cost modeling, benchmark comparison, and repeated walk-forward testing.

