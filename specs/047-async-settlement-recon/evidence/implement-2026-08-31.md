# Evidence 047

`pytest tests/unit/test_recon.py tests/unit/test_recon_http.py tests/unit/test_ledger.py tests/test_health.py` 34 passed. Combined recon+ledger coverage 87% (recon service 84%, ledger service 87%). Duplicate/late reported appends delta and keeps original 80-unit debit. Four unresolved reason codes. SLA expiry stays unresolved (available 460/500). Reverse without step-up rejected; originals retained after confirmed reverse.
