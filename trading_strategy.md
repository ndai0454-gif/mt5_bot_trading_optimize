# Trading Strategy Spec (Risk-first Approach)

## 1. Objective

Focus on: - Account Management - Risk Management - Long-term
survivability

------------------------------------------------------------------------

## 2. Core Rules

### 2.1 Entry Constraints

-   Every trade must include:
    -   Stop Loss (SL)
    -   Take Profit (TP)
-   Risk/Reward ratio: R:R ∈ \[1:2, 1:3\]

------------------------------------------------------------------------

### 2.2 Risk per Trade

-   risk_per_trade = 1% \* account_balance
-   Can be optimized later

------------------------------------------------------------------------

### 2.3 TP Splitting Logic

Split TP into 4 parts:

  TP Level   \% Volume
  ---------- -----------
  TP1        30%
  TP2        20%
  TP3        30%
  TP4        20%

------------------------------------------------------------------------

## 3. Scaling (Nhồi lệnh)

### 3.1 Conditions

-   Reached TP1 + TP2 (\>= 50% TP)

-   75% H1 candle confirmation (no reversal)

### 3.2 Max Orders

-   1 base + 3 scaling orders

### 3.3 SL Rule

-   Move SL to entry after scaling

------------------------------------------------------------------------

## 4. Flow

Base Order → TP1 hit → TP2 hit → activate scaling → Add Order 1 → move
SL base → entry → Add Order 2 → move SL Add1 → entry → Add Order 3 →
repeat

------------------------------------------------------------------------

## 5. Example

Account: \$1000\
Risk: \$10

Entry: 2000\
SL: 1990\
TP: 2020

TP: - TP1: +6 - TP2: +4 - TP3: +6 - TP4: +4

------------------------------------------------------------------------

## 6. Execution

1.  BUY @ 2000
2.  Price reaches 2010 → close 50%
3.  Add Order 1 @ 2010 → move SL base → 2000
4.  Add Order 2 when Order 1 reaches 50% TP
5.  Repeat up to 3 scaling orders

------------------------------------------------------------------------

## 7. Philosophy

-   Protect capital first
-   Scale only when winning
-   Never increase risk on losing trades
-   Turn trades risk-free ASAP
