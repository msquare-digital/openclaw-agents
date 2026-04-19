# Product Intake Routine

## Goal
New products should only be added when they are searchable and specific enough to monitor reliably.

## Rule
If critical information is missing, pricewatch must ask follow-up questions until the product can be searched with reasonable confidence.
Do not silently add vague or underspecified products as fully active watches.

## Minimum required information
A new product should have at least:
- product name or searchable query
- target price
- currency (default EUR if not stated)
- enough identifying detail to distinguish the exact product

## Common identifying details
Depending on category, ask for the missing specifics such as:
- brand
- model name
- storage size
- color
- variant
- generation or year
- EAN / SKU / product code
- shade / tone / size / volume
- condition (new, used, refurbished)
- region or edition
- useful aliases or alternate spellings
- known product URL if the user already has one

## Follow-up behavior
When something important is missing:
1. ask only for the missing information
2. keep the follow-up compact
3. continue asking until the product is searchable
4. only then add it as an active watch item

## If the product remains ambiguous
If multiple plausible products match and the user has not clarified the item:
- do not guess
- present the ambiguity clearly
- ask the user to choose or refine the product

## Good outcome
A product is ready to add when pricewatch can reasonably search for it without mixing it up with adjacent variants.
Prefer storing enough detail for both broad discovery and strict verification, for example one canonical name plus 2 to 3 realistic search aliases.

## Suggested intake summary after clarification
When the product becomes specific enough, confirm in a compact structured way:
- product
- target price
- key identifying details
- condition
- region
- notes
