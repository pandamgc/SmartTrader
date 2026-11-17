# Backtest: high-probability mode (build_hp_plan)

Symbols: HDFCBANK, RELIANCE, TCS, INFY, ICICIBANK, SBIN, LT, ITC, AXISBANK, BHARTIARTL. Train = entries before 2024-01-01; Test = entries on/after 2024-01-01.
Costs 0.2% round trip, max hold 20 days, stop assumed first on same-bar hits.
Parameters are chosen on TRAIN only (best train win rate with avg R > 0 and enough trades).

## Grid (train and test shown; test not used for selection)
```
 target_R  min_score  train_n  train_win%  train_avgR  train_PF  test_n  test_win%  test_avgR  test_PF
     0.75          3      258        61.2       -0.05      0.80     311       54.3      -0.22     0.53
     0.75          4      210        58.1       -0.05      0.76     267       47.6      -0.30     0.40
     0.75          5      101        54.5       -0.05      0.74     138       50.0      -0.25     0.44
     1.00          3      256        60.5       -0.03      0.84     310       52.3      -0.25     0.52
     1.00          4      210        58.6       -0.03      0.83     266       45.5      -0.33     0.39
     1.00          5      101        55.4       -0.01      0.85     138       47.8      -0.27     0.44
     1.50          3      255        60.4       -0.03      0.86     310       52.3      -0.24     0.53
     1.50          4      209        58.4       -0.02      0.86     266       45.5      -0.33     0.39
     1.50          5      100        55.0       -0.00      0.87     138       47.8      -0.27     0.44
```

No parameter set had enough profitable train trades. Nothing selected.