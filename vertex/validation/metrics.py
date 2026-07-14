"""Performance metrics — freshly implemented. Headline is SHARPE (scale-free).

The load-bearing additions over a naive backtest (and the explicit gap in v1) are the
**Probabilistic** and **Deflated** Sharpe Ratios (Bailey & Lopez de Prado, 2012/2014):

  • PSR  — probability the TRUE Sharpe exceeds a benchmark, correcting the point estimate
           for sample length AND return skew/fat tails (a high Sharpe from a few lucky
           fat-tailed months is penalised).
  • DSR  — PSR evaluated against the *expected maximum* Sharpe you'd see by chance after
           trying N strategy variants. This is the honest defence against the False
           Strategy Theorem: try enough specs and one looks great by luck; DSR discounts
           for exactly that. Feed it the number of variants we actually tried (trials.md).

norm_ppf uses Acklam's rational approximation (a standard public numerical routine).
"""

import math

import numpy as np

TRADING_DAYS = 252
_SQRT2 = math.sqrt(2.0)
_EULER = 0.5772156649015329  # Euler-Mascheroni constant


def _clean(daily):
    a = np.asarray(daily, dtype=float)
    return a[~np.isnan(a)]


def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / _SQRT2))


def norm_ppf(p):
    """Inverse standard-normal CDF (Acklam's rational approximation)."""
    if p <= 0.0:
        return -math.inf
    if p >= 1.0:
        return math.inf
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p <= phigh:
        q = p - 0.5
        r = q * q
        return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
               (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    q = math.sqrt(-2 * math.log(1 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
        ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)


def sharpe(daily, annualize=True):
    d = _clean(daily)
    if len(d) < 2:
        return 0.0
    sd = d.std(ddof=1)
    if sd == 0:
        return 0.0
    s = d.mean() / sd
    return s * math.sqrt(TRADING_DAYS) if annualize else s


def ann_return(daily):
    d = _clean(daily)
    return float(d.mean() * TRADING_DAYS) if len(d) else 0.0


def ann_vol(daily):
    d = _clean(daily)
    return float(d.std(ddof=1) * math.sqrt(TRADING_DAYS)) if len(d) > 1 else 0.0


def max_drawdown(daily):
    d = _clean(daily)
    if not len(d):
        return 0.0
    curve = np.cumprod(1 + d)
    peak = np.maximum.accumulate(curve)
    return float((curve / peak - 1).min())


def hit_rate(daily):
    d = _clean(daily)
    return float((d > 0).mean()) if len(d) else 0.0


def _skew_kurt(d):
    n = len(d)
    s = d.std(ddof=0)
    if s == 0 or n < 3:
        return 0.0, 3.0
    z = (d - d.mean()) / s
    return float((z ** 3).mean()), float((z ** 4).mean())   # kurtosis: normal = 3


def summary(daily):
    """Core metrics dict (raw scale). Sharpe is scale-free; ann_ret/maxDD scale with leverage."""
    d = _clean(daily)
    return {"n": len(d), "sharpe": sharpe(d), "ann_ret": ann_return(d),
            "ann_vol": ann_vol(d), "maxdd": max_drawdown(d), "hit": hit_rate(d)}


def probabilistic_sharpe(daily, sr_benchmark_ann=0.0):
    """P(true Sharpe > benchmark), correcting for sample size, skew and kurtosis."""
    d = _clean(daily)
    n = len(d)
    if n < 3:
        return 0.0
    sr = sharpe(d, annualize=False)                 # per-period
    srb = sr_benchmark_ann / math.sqrt(TRADING_DAYS)
    g3, g4 = _skew_kurt(d)
    denom = math.sqrt(max(1e-12, 1 - g3 * sr + (g4 - 1) / 4.0 * sr * sr))
    z = (sr - srb) * math.sqrt(n - 1) / denom
    return norm_cdf(z)


def expected_max_sharpe_ann(n_trials, trials_sr_std_ann):
    """Bailey-LdP expected maximum Sharpe under the null across N independent trials."""
    N = max(2, int(n_trials))
    e = math.e
    return trials_sr_std_ann * ((1 - _EULER) * norm_ppf(1 - 1.0 / N)
                                + _EULER * norm_ppf(1 - 1.0 / (N * e)))


def deflated_sharpe(daily, n_trials, trials_sr_std_ann=None):
    """DSR: PSR against the expected-max Sharpe from N trials. ~P(the skill is real after
    accounting for having searched N variants). trials_sr_std_ann ideally = the observed
    std of the trial Sharpes (from trials.md); the fallback is the null sampling std."""
    d = _clean(daily)
    n = len(d)
    if n < 3 or n_trials < 1:
        return 0.0
    if trials_sr_std_ann is None:
        trials_sr_std_ann = math.sqrt(TRADING_DAYS / (n - 1))   # null sampling std of an annual Sharpe
    sr0_ann = expected_max_sharpe_ann(n_trials, trials_sr_std_ann)
    return probabilistic_sharpe(d, sr_benchmark_ann=sr0_ann)
