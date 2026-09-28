# Task 31 — Declared JWT TTL and credential residuals

Recorded 28 September 2026 on the **Apple M3 Pro** (same host as [`12-reproducibility.md`](12-reproducibility.md): Darwin 25.5.0). Lima VM numbers are not used in this file. Paper 1 `TABLE=` headline tables are not rewritten here; paste from `make paper-tables TABLE=credential` and `TABLE=step-split`.

## Duration policy

Constants from `rig/agent/duration_policy.yaml` (Task 26 Tempo `verify` p95s, M3 Pro, full seeds 1–10):

| tool | n | p95 (ms) |
| --- | ---: | ---: |
| records | 203 | 0.1997494 |
| search | 57 | 0.2233414 |
| notify | 30 | 0.98716235 |

Floor 500 ms; ×3; task slack ×1.5; SPIRE min JWT TTL 1 s. Floor binds every tool, so declared **task duration = 23 s** and **step duration = 1 s**. There is no 1800 s default. JWT-SVID TTL is the declared duration for the run's granularity, then `max(requested, 1 s)`.

Study-design amendment: [`docs/study-design.md`](../study-design.md) dated 28 September 2026.

## Metric definitions

| Quantity | Definition |
| --- | --- |
| `τ` | `exp − iat` of the JWT-SVID (`tau_definition: jwt_ttl`). Flat is the 24 h SA token (`τ = 86400` s, `sa_token`). |
| `T` | first to last tool call |
| `residual_credential_s` | `exp − task_end` |
| `residual_reach_ms` | `policy_removed_at − task_end` |

`TABLE=credential` refuses mixed `tau_definition` within a cell. Pre-T25 full/step seeds 1–10 were copied to `runs/results/_superseded-pre-t25/` with `superseded_by: task31` and re-run.

## Exclusive cluster matrix

`/tmp/ba-campaign.lock` held for the whole 25-job set. `source=cluster`, 25/25 provenance-ok.

| cell | seeds | run id |
| --- | --- | --- |
| full task | 1–10 | `long-multistep-full-seed{n}` |
| full step probe-on | 1–10 | `long-multistep-full-step-seed{n}` |
| full step probe-off | 1–5 | `long-multistep-full-step-noprobe-seed{n}` |

## Seed 9 (31.3)

The Task 26 step-granularity stall (`d_max` 901990.4 ms) did not recur. This campaign's seed-9 `d_max` is 209.3 ms. Median `d_max` of the other nine step seeds is 135.6 ms. Ratio 1.54, below the 10× re-run/exclude threshold. Seed 9 is kept. Seed 5 has a single-boundary `d_max` of 3363 ms; per-boundary medians remain in the 47–79 ms IQR and that seed is not excluded.

## `d` versus `propagation` (31.4)

These are two instruments. They are not one clock with two names.

| Quantity | Timestamp pair | What |
| --- | --- | --- |
| `d` (controller p/q/d) | `cnp_wait_started → cnp_valid` | Host kubectl poll of the egress CNP until `status.conditions[type=Valid]=True`. Same instrument as Task 26 `d_ms_mean` / `d_ms_max`. |
| `propagation` (step-split) | `declaration_applied → first_enforced` | `kubectl apply` of TaskDeclaration + CNP **returned** → the same CNP Valid observation. SPIRE mint and APISIX are not on this clock (`svid_reissue` / `other`). |

On this campaign the pairs agree: per-boundary median `d` 72.5 ms [47.3, 78.7] and median `propagation` 72.6 ms [47.3, 78.7] over **290** probe-on boundaries (10 seeds × 29 declaration updates; injection step 15 omitted). Task 26's ~48 ms median `d` is the same quantity. The earlier ~2.9 s/boundary “propagation” included SPIRE/APISIX on the clock and is not this `d`. Named clocks plus `other` reconcile with each boundary total within 5% (observed 0%).

## TABLE=credential

`make paper-tables TABLE=credential`. Caption n is per cell, never 97.

```
% --- Credentials (Task 31) ---
% Caption: Credentials (Task 31). source=cluster (flat n=10; full n=10; full-step n=10). τ = exp − iat of the JWT-SVID (full/full-step) or 24 h SA token (flat, τ = 86400 s). T = first to last tool call. residual_credential_s = exp − task_end; residual_reach_ms = policy_removed_at − task_end. No mixed τ definitions.
\begin{tabular}{lrlrrrrr}
cell & $n$ & $\tau$ def & median $\tau$ (s) [IQR] & median $T$ (s) [IQR] & median $\tau/T$ [IQR] & median residual\_credential\_s [IQR] & median residual\_reach\_ms [IQR] \\
\hline
flat & 10 & sa_token & 86400.000 [86400.000, 86400.000] & 0.285 [0.222, 0.335] & 303704.719 [258789.707, 395146.259] & \textemdash{} & \textemdash{} \\
full & 10 & jwt_ttl & 23.000 [23.000, 23.000] & 0.175 [0.164, 0.200] & 131.776 [115.168, 139.973] & 21.947 [21.879, 22.093] & 148.0 [142.4, 151.7] \\
full-step & 10 & jwt_ttl & 1.000 [1.000, 1.000] & 241.305 [185.881, 248.783] & 0.004 [0.004, 0.005] & -248.367 [-255.735, -191.770] & 235.6 [203.1, 258.7] \\
\end{tabular}
```

Full-step `residual_credential_s` is negative because `T` is first-to-last tool call over the 30-step run (~241 s) while each step JWT is 1 s: the credential expires during the work. Residual reach (~236 ms) is segment collapse after `task_end`.

## TABLE=step-split

`make paper-tables TABLE=step-split`. Caption n is boundaries, never 97.

```
% --- Step cost split (Task 31) ---
% Caption: Step cost split (Task 31). source=cluster (n=435 boundaries; probe-on n=290; probe-off n=145). Units are per boundary, not per run. `d` = cnp_wait_started → cnp_valid. `propagation` = declaration apply returned → first enforced (CNP Valid). Named clocks plus `other` sum to the boundary total within 5% on every boundary.
\begin{tabular}{lrl}
component & $n$ (boundaries) & median [IQR] (ms) \\
\hline
propagation & 290 & 72.6 [47.3, 78.7] \\
svid_reissue & 290 & 333.8 [210.0, 398.6] \\
probe & 290 & 5774.9 [4997.3, 6178.7] \\
other & 290 & 379.5 [243.0, 430.4] \\
d (CNP Valid wait) & 290 & 72.5 [47.3, 78.7] \\
boundary total (probe on) & 290 & 6665.4 [5505.0, 7126.8] \\
boundary total (probe off) & 145 & 838.5 [758.6, 990.2] \\
\end{tabular}
```

Probe-off `|S|=3` (FORWARDED flows only). Probe-on TCP inventory still inflates `|S|` on some seeds; that is not a credential number.

## Host / lock

| Item | Value |
| --- | --- |
| Host | Apple M3 Pro, Darwin 25.5.0 (`Rinus-MBP-M3.local`) |
| Exclusive | yes (`/tmp/ba-campaign.lock` held for the 25-job matrix) |
| Jobs | 25 ran, 0 skipped, 0 failed |
| Branch | `task-31-credential` |
