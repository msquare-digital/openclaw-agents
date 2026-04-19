# pricewatch Trust Policy

## Goal
pricewatch may consider dynamically discovered shops, but only when they are sufficiently trustworthy and can plausibly deliver to Wuppertal, Germany.

## Default principle
A shop should not be accepted just because it offers the lowest price.
A low price is only relevant when the seller and the shop pass basic legitimacy checks.

## Shop classes

### Class A: well-known retailers
Examples: established retailers or brand-direct shops.

Policy:
- may be used with standard checks
- still verify delivery and product match
- still include shipping in the effective price when possible

### Class B: marketplaces
Examples: Amazon Marketplace, eBay, similar seller platforms.

Policy:
- assess the individual seller, not only the platform
- require stronger seller checks than for Class A
- include seller quality notes in alerts when relevant

### Class C: lesser-known shops
Examples: smaller standalone shops not already known to be trustworthy.

Policy:
- require stricter trust checks before alerting
- if trust remains uncertain, do not alert as a normal finding
- optionally report as `price interesting but trust unconfirmed`

## Hard reject rules
Do not alert on a shop when one of these is true:
- no plausible legal imprint or business identity
- no shipping to Germany or Wuppertal cannot be reasonably served
- suspiciously incomplete contact details
- payment options look unsafe or unusually limited
- price looks implausibly far below the market without other trust signals
- strong negative reputation signals are found
- listing details conflict with the expected product or variant

## Minimum trust checks
At least two trust signals must be present for normal consideration.

Preferred trust signals:
- legal imprint or clearly attributable business identity
- secure checkout over HTTPS
- plausible contact details
- standard payment methods
- external reputation signal
- clear return or cancellation policy

## Marketplace rules

### Amazon Marketplace
Preferred order:
1. Sold by Amazon
2. Brand store or clearly established seller
3. Marketplace seller only if seller quality is strong

For marketplace sellers, prefer:
- very high rating percentage
- meaningful rating volume
- business identity or store transparency
- no obvious listing inconsistencies

### eBay
Prefer sellers with:
- high positive feedback percentage
- meaningful feedback volume
- business seller status when available
- clear item condition and return information
- realistic photos and description quality

Avoid:
- new or low-history sellers for expensive items
- vague item condition text
- listings with mismatched title and product details

## Unknown-shop handling
For unknown shops, require at least three positive trust signals before alerting normally.
If the price is interesting but trust is still unclear, downgrade the result instead of treating it as a normal hit.

## Suspicious-price rule
If a price is dramatically below other credible offers, treat it as suspicious until trust is confirmed.
A cheap offer is not automatically a good offer.

## Alert policy
When the shop is not obviously top-tier, alerts should include a short trust note, for example:
- `shop trust: medium, seller cross-checked`
- `shop trust: low, interesting price but not yet confirmed`

## Delivery policy
A shop is relevant only if delivery to Wuppertal is available or strongly likely for Germany.
If delivery is unclear, mark the result as incomplete rather than fully valid.
