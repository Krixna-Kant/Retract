| Method | Precision | Recall | F1 | Exact-match scenarios |
|---|---|---|---|---|
| `keyword_topk` | 0.63 | 0.47 | 0.54 | 5/16 |
| `one_hop` | 0.67 | 0.50 | 0.57 | 4/16 |
| `transitive` | 0.77 | 1.00 | 0.87 | 10/16 |
| `naive_fixpoint` | 1.00 | 0.89 | 0.94 | 14/16 |
| `retract` | 1.00 | 1.00 | 1.00 | 16/16 |

Per scenario (exact match of the invalidated set):

| Scenario | `keyword_topk` | `one_hop` | `transitive` | `naive_fixpoint` | `retract` |
|---|---|---|---|---|---|
| 01_single_hop | yes | yes | yes | yes | yes |
| 02_multi_hop | no (+0 / -2) | no (+0 / -2) | yes | yes | yes |
| 03_independent_support_survives | no (+1 / -0) | no (+1 / -0) | no (+1 / -0) | yes | yes |
| 04_shared_support | no (+1 / -0) | no (+1 / -0) | no (+1 / -0) | yes | yes |
| 05_implicit_dependency | no (+0 / -2) | no (+0 / -2) | yes | yes | yes |
| 06_diamond | yes | no (+0 / -1) | yes | yes | yes |
| 07_diamond_with_rescue | no (+2 / -0) | no (+1 / -0) | no (+2 / -0) | yes | yes |
| 08_circular_support | yes | no (+0 / -1) | yes | no (+0 / -2) | yes |
| 09_circular_with_real_root | no (+2 / -0) | no (+1 / -0) | no (+2 / -0) | yes | yes |
| 10_decision_reversal | no (+0 / -2) | no (+0 / -1) | yes | yes | yes |
| 11_decision_plus_source | no (+1 / -0) | no (+1 / -0) | no (+1 / -0) | yes | yes |
| 12_dead_intermediate_cannot_rescue | yes | yes | yes | yes | yes |
| 13_other_support_already_revoked | yes | yes | yes | yes | yes |
| 14_deep_chain | no (+0 / -6) | no (+0 / -6) | yes | yes | yes |
| 15_keyword_trap | no (+2 / -0) | yes | yes | yes | yes |
| 16_northwind_memo (full graph) | no (+1 / -7) | no (+4 / -5) | no (+4 / -0) | no (+0 / -2) | yes |

`+x / -y` = x false positives, y missed claims.
LLM provider for `llm_topk`: not run (no key configured)
