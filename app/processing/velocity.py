"""Auditable ordinary least-squares velocity fits in caller-specified units."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class VelocityFit:
    slope: float
    intercept: float
    time_origin: float
    stderr: float | None
    residuals: np.ndarray
    fitted: np.ndarray


def fit_velocity(time: np.ndarray, distance: np.ndarray) -> VelocityFit:
    """Fit s = v*(t-t0)+b. Standard error assumes independent equal-variance
    distance errors and exact times. It excludes WCS, tracing and projection
    systematics. Two points cannot estimate a residual-based standard error.
    """
    t, s = np.asarray(time, float), np.asarray(distance, float)
    if t.ndim != 1 or s.shape != t.shape or t.size < 2 or not np.all(np.isfinite([t, s])):
        raise ValueError("Choose at least two finite time/distance points.")
    t0 = float(t.mean()); x = t - t0
    ssx = float(x @ x)
    if ssx <= np.finfo(float).eps:
        raise ValueError("Velocity requires distinct times.")
    v, b = np.linalg.lstsq(np.column_stack((x, np.ones(len(x)))), s, rcond=None)[0]
    fitted = v*x + b
    residual = s - fitted
    error = float(np.sqrt((residual @ residual) / (len(t)-2) / ssx)) if len(t)>2 else None
    return VelocityFit(float(v), float(b), t0, error, residual, fitted)


def fit_motion(time: np.ndarray, distance: np.ndarray, acceleration: bool = False, *, allow_exact: bool = False) -> dict:
    """OLS polynomial in centered, scaled time; band is 1σ uncertainty of the
    fitted mean, NOT prediction scatter. Constant acceleration is 2*c2/scale².
    Requires residual degrees of freedom (3 linear / 4 quadratic points).
    allow_exact permits a three-point quadratic with unavailable uncertainty.
    """
    t, s = np.asarray(time, float), np.asarray(distance, float)
    degree = 2 if acceleration else 1
    minimum = degree+1 if allow_exact else degree+2
    if t.ndim != 1 or s.shape != t.shape or len(t) < minimum or not np.all(np.isfinite([t, s])):
        raise ValueError(f"Choose at least {degree+2} finite points for this fit.")
    scale = float(np.ptp(t)); origin = float(t.mean())
    if scale <= 0:
        raise ValueError("Choose distinct times.")
    x = (t-origin)/scale
    design = np.polynomial.polynomial.polyvander(x, degree)
    coef, _, rank, _ = np.linalg.lstsq(design, s, rcond=None)
    if rank != degree+1:
        raise ValueError("Not enough distinct times for this fit.")
    residual = s-design@coef
    dof = len(t)-degree-1
    variance = float(residual@residual)/dof if dof > 0 else float("nan")
    cov = variance * np.linalg.pinv(design.T@design)
    grid = np.linspace(t.min(), t.max(), 100)
    basis = np.polynomial.polynomial.polyvander((grid-origin)/scale, degree)
    fitted = basis@coef
    sigma = np.sqrt(np.maximum(0, np.einsum('ij,jk,ik->i', basis, cov, basis)))
    a = float(2*coef[2]/scale**2) if acceleration else None
    v_edges = coef[1]/scale + (a*(np.array([t.min(), t.max()])-origin) if a is not None else np.zeros(2))
    derivative = np.array([0, 1/scale, 2*((t.min()+t.max())/2-origin)/scale**2]) if acceleration else np.array([0, 1/scale])
    return dict(time=grid, fitted=fitted, sigma=sigma, residuals=residual,
                acceleration=a, acceleration_stderr=float(2*np.sqrt(cov[2,2])/scale**2) if acceleration and dof > 0 else None,
                reverses_direction=bool(v_edges[0]*v_edges[1]<0),
                velocity_stderr=float(np.sqrt(max(0, derivative@cov@derivative))) if dof > 0 else None)
