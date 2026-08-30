# Data Model：费率版本

## RateVersion

status: draft | previewed | approved | published | superseded  
buyer_multiplier_bps, seller_quote_min_bps, seller_quote_max_bps  
rows: RateRow[]（dimension 费率）

## RateRow

(provider, model, endpoint_id, dimension, region, currency, unit, rate_minor_units, valid_from, valid_to)

## SellerQuote

(seller_id, rate_version, multiplier_bps) 必须 ∈ [min, max]

## PriceLock

request_id → (rate_version, buyer_bps, seller_bps) 不可变

## QuoteResult

base_minor, buyer_debit, seller_earning, spread, status reported|rated|unresolved
