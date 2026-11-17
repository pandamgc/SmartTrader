# Backtest report: Agents 1-9 price logic

Symbols: HDFCBANK, RELIANCE, TCS, INFY, ICICIBANK, SBIN, LT, ITC, AXISBANK, BHARTIARTL. Walk-forward, no look-ahead, long-only, one position per stock.
Costs: 0.2% round trip. Same-bar stop/target: stop assumed first. Pullback limit valid 10 days, max hold 30 days.
Agent 10 (OI) not backtested: no historical option-chain OI available.

## Overall
```
trades           870.00
win_rate_%        52.40
avg_R             -0.25
avg_ret_%          0.18
profit_factor      1.18
max_dd_%         -53.70
avg_bars           4.80
dtype: float64
```

## By action
```
                 trades  win_rate_%  avg_R  avg_ret_%  profit_factor  max_dd_%  avg_bars
BUY               269.0        50.9  -1.16       0.04           1.04     -40.9       5.1
BUY ON PULLBACK   601.0        53.1   0.16       0.25           1.25     -38.8       4.6
```

## By symbol
```
            trades  win_rate_%  avg_R  avg_ret_%  profit_factor  max_dd_%  avg_bars
AXISBANK      91.0        54.9  -3.49       0.11           1.10     -17.8       4.7
BHARTIARTL   104.0        54.8   0.13       0.29           1.30     -16.8       5.1
HDFCBANK      83.0        42.2  -0.07      -0.15           0.86     -19.1       4.3
ICICIBANK     98.0        54.1   0.21       0.19           1.21     -17.6       5.2
INFY          72.0        47.2   0.01       0.05           1.04     -20.2       4.5
ITC           78.0        55.1   0.22       0.44           1.49     -15.5       4.2
LT            96.0        58.3   0.27       0.52           1.53     -13.6       4.7
RELIANCE      82.0        53.7   0.15       0.23           1.23     -12.6       4.8
SBIN          96.0        57.3   0.33       0.27           1.25     -18.3       5.3
TCS           70.0        41.4  -0.17      -0.25           0.79     -26.0       4.5
```

## Exit reasons
```
exit_reason
stop             404
T2               277
stop_after_T1    178
time              11
Name: count, dtype: int64
```

## Signal quality: average forward return (%) after each verdict, all days
Unconditional average (every day):
```
fwd_5d_pct     0.36
fwd_10d_pct    0.67
fwd_20d_pct    1.28
dtype: float64
```
By verdict:
```
                         fwd_5d_pct  fwd_10d_pct  fwd_20d_pct  days
action                                                             
AVOID / EXIT IF HOLDING        0.45         0.85         1.56  3353
BUY                            0.31         0.64         0.66   285
BUY ON PULLBACK                0.69         1.01         1.55   824
WAIT                           0.09         0.24         0.80  2037
```

## Buy & hold over the same window (%)
```
HDFCBANK       14.2
RELIANCE       26.7
TCS           -22.5
INFY          -23.1
ICICIBANK     126.2
SBIN          154.2
LT            143.2
ITC            68.8
AXISBANK      100.3
BHARTIARTL    217.0
dtype: float64
```