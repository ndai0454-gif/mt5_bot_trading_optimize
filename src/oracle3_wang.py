"""Oracle3 Wang Transform Algorithm
==================================
This module implements the core pricing engine from Oracle3, adapted for MT5 Spot trading.
It uses the Wang Transform to adjust baseline probabilities (e.g., historical win rate or ML predictions)
by incorporating market microstructure data like Tick Volume and Spread (Liquidity).

The core idea is that market prices (or signals) are biased by Favorite-Longshot Bias.
This algorithm calculates the bias factor (Lambda) and extracts the "True Probability" (Fair Value).

Formula:
    p_star = Φ( Φ^(-1)(p_mkt) - λ )
    λ = β0 + β1*ln(1+V) + β2*ln(1+D) - β3*|p_mkt - 0.5|

Where:
    Φ is the Standard Normal CDF
    Φ^(-1) is the Inverse Standard Normal CDF (Probit)
"""

import math
import logging
from statistics import NormalDist
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class WangCoefficients:
    """Coefficients for the Hierarchical Lambda Model."""
    beta_0: float = 0.05   # Base bias
    beta_1: float = 0.02   # Volume sensitivity
    beta_2: float = 0.015  # Depth/Liquidity sensitivity
    beta_3: float = 0.10   # Extremity bias penalty

class OracleWangTransform:
    def __init__(self, coeffs: WangCoefficients = None):
        self.coeffs = coeffs or WangCoefficients()
        # NormalDist() provides standard normal CDF and inverse CDF built into Python
        self.norm = NormalDist(mu=0.0, sigma=1.0)
        
    def _probit(self, p: float) -> float:
        """Inverse Standard Normal CDF (Φ^(-1))"""
        # Clamp probability to avoid infinity
        p = max(0.0001, min(0.9999, p))
        return self.norm.inv_cdf(p)
        
    def _cdf(self, x: float) -> float:
        """Standard Normal CDF (Φ)"""
        return self.norm.cdf(x)

    def calculate_lambda(self, p_mkt: float, volume_norm: float, spread_norm: float) -> float:
        """
        Calculate the bias coefficient (λ) based on the hierarchical model.
        
        Args:
            p_mkt (float): Baseline market probability (0.0 to 1.0)
            volume_norm (float): Normalized volume (V)
            spread_norm (float): Normalized spread. Lower spread = Higher depth (D).
                                 We will inverse spread to represent depth.
        """
        # Convert spread to a depth proxy: tighter spread = higher depth.
        # Assuming spread_norm is scaled (e.g. 0.0 to 1.0 where 1.0 is extremely high spread)
        # Depth D = 1.0 - spread_norm (if spread is normalized), or just 1/spread
        # For safety, we use max(0, 1.0 - spread_norm) as a proxy for D.
        depth_proxy = max(0.0, 1.0 - spread_norm)
        
        bias_base = self.coeffs.beta_0
        vol_effect = self.coeffs.beta_1 * math.log(1.0 + volume_norm)
        depth_effect = self.coeffs.beta_2 * math.log(1.0 + depth_proxy)
        extremity_penalty = self.coeffs.beta_3 * abs(p_mkt - 0.5)
        
        # Oracle3 hierarchical lambda formula
        lam = bias_base + vol_effect + depth_effect - extremity_penalty
        return lam

    def get_true_probability(self, p_mkt: float, volume_norm: float, spread_norm: float) -> float:
        """
        Apply the Wang Transform to extract the True Probability (Fair Value p*).
        
        Args:
            p_mkt (float): Baseline probability (e.g. historical win rate or RSI/100)
            volume_norm (float): Normalized tick volume for the current bar
            spread_norm (float): Normalized spread (current spread / average spread)
            
        Returns:
            float: True Probability (p*) adjusted for market microstructure.
        """
        # Calculate lambda (bias)
        lam = self.calculate_lambda(p_mkt, volume_norm, spread_norm)
        
        # Apply inverse transform
        probit_p_mkt = self._probit(p_mkt)
        
        # p* = Φ( Φ^(-1)(p_mkt) - λ )
        p_star = self._cdf(probit_p_mkt - lam)
        
        logger.debug(f"Wang Transform: p_mkt={p_mkt:.4f}, λ={lam:.4f} -> p*={p_star:.4f}")
        return p_star

if __name__ == "__main__":
    # Quick Test
    wang = OracleWangTransform()
    
    # Example 1: 55% Win Rate, High Volume, Tight Spread (Low spread_norm)
    p1 = wang.get_true_probability(p_mkt=0.55, volume_norm=0.8, spread_norm=0.2)
    print(f"High Liquidity Trade: 55% -> {p1*100:.2f}%")
    
    # Example 2: 55% Win Rate, Low Volume, High Spread (High spread_norm)
    p2 = wang.get_true_probability(p_mkt=0.55, volume_norm=0.1, spread_norm=0.9)
    print(f"Low Liquidity Trade:  55% -> {p2*100:.2f}%")
