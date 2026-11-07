# Methods

## Market and network context

Binance inputs are daily ZIP archives verified against provider SHA-256 files.
Source microseconds are converted to UTC; hourly or daily candles are concatenated
in pair/time order. Quote currencies and provider numeric strings are preserved.
Raydium values are selected by provider timestamp for the recorded WSOL/USDC pool.
The liquidity measure is the provider's single-pool USD aggregate.

growthepie Base fees and transaction counts are selected for 21 UTC days. Fees use
ETH. The provider's transaction-count definition excludes zero-gas-price transactions;
historical operator-fee treatment remains unresolved in the retained methodology.
These tables reproduce the provider's indexed aggregates.

## Solana sampled transaction counts

Each UTC hour is a stratum. The fixed sample contains 50 produced finalized blocks
per hour, selected without replacement before observing transaction outcomes.
Returned transactions include votes and failures. The released vote-program-reference
field checks account-key presence and serves as a proxy.

For population size N, sample size n=50, sample mean ybar and sample variance s²
with denominator n−1, the estimated total is N × ybar. Its standard error is
N × sqrt((1−n/N) × s²/n). The approximate 95% interval is the estimate plus or minus
2.009575234489209 standard errors, with the lower bound clipped to zero.
The same calculation is applied to total, successful and failed transaction counts.
TPS divides the total estimate by 3,600. Failure share divides estimated failed
counts by estimated total counts. Fractional estimates are retained.

The uncertainty calculation is conditional on the provider-returned frame and its
ledger-time hour boundaries. The released inputs support reaggregation of the fixed
sample. The original full responses and external-provider comparisons are retained
in the research workspace; this package's verification starts from count summaries.

## BSC price derivatives

Hourly log return is ln(close_t / close_(t−1)). Rolling volatility is the sample
standard deviation, with denominator 23, of 24 consecutive hourly log returns.
The value is unannualized. Both measures become observable at candle end.
The first return and first 24 volatility values remain empty.

## News and mechanism curation

Researchers selected publications, checked their primary references, and wrote
English facts with explicit status and scope. Statistical claims preserve the
publisher, period and denominator; scheduled events preserve their announced status.
The release contains the approved curated records and their source locators.
News coverage is a selected collection. The reproduction program checks the frozen
export; source interpretation is a human review step.

Mechanism records identify the relevant version, source section and applicability.
Research-window subsets of the Solana master table are not stored as separate tables.
They can be derived by selecting the latest pre-window document for each rule plus
all selected in-window versions. Historical-role records stay in the master.
BSC includes the 22 records approved by the inclusion decision and omits F13.
Source-history tables retain selected document or commit dates.

## Shared market and macroeconomic data

Coin Metrics current-supply and estimated-supply capitalization retain distinct
fields. SOL current-supply capitalization is unavailable in this snapshot.
Reported asset trading volume uses the provider's per-asset definition.
CMC global aggregates preserve both 24-hour volume definitions and BTC/ETH dominance.
CoinSpectrum captures preserve both generation time and archive-capture time.

EFFR uses the effective date. CPI-U and unemployment observations use the reference
month. Treasury values are the interpolated 10-year par yield, in percent.
The BLS archived-release table is manually transcribed; the code converts its stated
08:30 New York embargo ends to UTC using the relevant daylight-saving rule.
Archived releases may contain later corrections, so the retained values describe
the consulted archive version. Unknown actual publication timestamps remain empty.

## Second-level market calculations

Binance Vision one-second candles are checked against their provider SHA-256
files. Simple returns are `close[t]/close[t-1]-1`; log returns are the natural
logarithm of that ratio. `rolling_24h_return_std` uses the sample standard
deviation (`ddof=1`) of 86,400 consecutive log returns.
`realized_volatility_24h` is the square root of their sum of squares. Both
are dimensionless and unannualized, and include source closes without trades.
There is no pre-window imputation. Initial missing values and the distinction
between candle end and archive availability are retained.

## AWS-derived second-level calculations

Transactions are assigned to the integer second of their block timestamp. Blocks are checked
for contiguous heights and parent-hash linkage across all 21 dates. Base receipt positions
are exhaustive, and each block's receipt gas sum equals its header. Base execution fees are
`gasUsed * effectiveGasPrice`, including failed transactions. Operator fees are not in the
AWS receipt schema, so only named components and their subtotal appear. BSC transaction `gas`
is a limit rather than gas consumed, so no BSC fee is derived.

Pool reserves replay Sync events in block and log order from a historical opening state, and
21 daily closing states are checked. `liquidity_usdc` multiplies the WETH reserve by the
Binance ETH/USDC close, using ETH as a WETH price proxy, and adds the USDC reserve.
Input fees apply the canonical 0.3% Uniswap V2 charge to every Swap event input.
