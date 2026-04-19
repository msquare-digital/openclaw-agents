# Discovery and Check Architecture

## Goal
Reduce empty runs by separating broad shop discovery from recurring price checks.

## Phase 1: Discovery
Use when:
- a product has no known direct URLs
- existing URLs are stale, blocked, or ambiguous
- the user adds a new product

Discovery should:
1. search broadly using canonical name, aliases, and searchable queries
2. prefer direct product pages over search pages
3. verify variant, price, shipping plausibility, and trust
4. store successful product URLs in `state/discovered-urls.json`
5. update `watchlist.yaml` `knownUrls` when a URL is stable and clearly tied to the product
6. classify each source as `found`, `no_match`, `blocked`, `ambiguous`, `found_but_untrusted`, `shipping_unclear`, or `variant_mismatch`

## Phase 2: Check
Use when:
- a product already has one or more known direct URLs
- the goal is recurring monitoring, not fresh web exploration

Check should:
1. read `knownUrls` from `watchlist.yaml`
2. fall back to `state/discovered-urls.json` if needed
3. fetch only the most promising URLs first
4. compare current price against target thresholds
5. emit alerts only for verified, trusted, variant-correct offers
6. avoid repeating full discovery unless URL coverage is missing or degraded

## Source Backoff
If a source returns repeated `blocked` results:
- do not count it as `not found`
- reduce its priority temporarily
- retry later instead of hammering it every run

## Skill Roles
- `ecommerce-price-watcher`: primary for URL-first monitoring and recurring checks
- `shopping-price-drop-coupon-scout`: coupon and official-offer supplement
- `competitor-price-tracker`: optional broader market context

## Desired Outcome
The user should increasingly see:
- fewer total blocked checks per run
- more stable direct URL monitoring
- clearer distinction between environment problems and genuine no-match situations
