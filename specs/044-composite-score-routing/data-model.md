# Data Model

## Policy

version, weights{health,latency,capacity,price}, explore_bps

## Signals

connection_id, health, latency_ms?, remaining?, declared?, seller_bps?

## Row

connection_id + 四因子整数 + total + reason

## Decision

policy_version, seed, winner, reason, scores[]
