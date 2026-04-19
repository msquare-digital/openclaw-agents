---
name: inbox_cleaner
description: Safely analyze, triage, and clean an email inbox with preview-first behavior and strict protection for important mail.
---

# Inbox Cleaner

Use this skill when the user wants help with:
- cleaning up an email inbox
- reviewing a large mailbox
- finding newsletters, promotions, and repetitive notifications
- identifying important emails
- building safe email cleanup rules
- preparing a daily inbox triage workflow

## Purpose

This skill helps the agent reduce inbox clutter **without causing damage**.

The default behavior is:
- analyze first
- classify conservatively
- preview before actions
- protect important mail
- prefer reversible actions

## Core rules

Always follow these rules when this skill is active:

- Do not permanently delete emails by default
- Do not send, reply, forward, or unsubscribe by default
- Do not bulk-change a mailbox without a preview
- Prefer read → classify → summarize → propose → confirm → execute
- If uncertain whether a message is important, preserve it
- Human-written mail is higher priority than machine-generated mail
- Financial, legal, security, tax, medical, account, and personal mail must be treated as sensitive
- Reversible actions are preferred over destructive actions
- "Needs review" is better than a wrong classification

## Classification categories

Unless the user requests a different scheme, classify emails into:

- Personal
- Important human email
- Work / business
- Bills / invoices / receipts
- Orders / deliveries
- Notifications
- Newsletters
- Promotions / marketing
- Security / login / account
- Spam / likely low value
- Needs review

## Safe operating sequence

When asked to clean or organize an inbox, use this sequence:

1. Inspect the mailbox or requested subset
2. Identify major sender groups and message types
3. Classify messages conservatively
4. Highlight urgent or important items first
5. Propose rules for cleanup
6. Show a preview of any non-trivial action
7. Wait for approval before bulk changes
8. Execute only approved changes
9. Report exactly what was changed

Never skip the preview step for:
- archive in bulk
- trash in bulk
- label in bulk
- mark-read in bulk
- unsubscribe actions
- mailbox rule changes

## What counts as important

Treat a message as important if it appears to involve:

- direct human communication
- deadlines, appointments, travel, or deliveries
- invoices, receipts, refunds, taxes, or contracts
- password resets, MFA, login alerts, or account warnings
- banking, insurance, government, work, or legal matters
- named personal contacts
- anything that looks unfamiliar but consequential

If an email might be important, keep it.

## Bulk clutter detection

Look for:

- recurring senders with high volume
- newsletters older than the user’s useful reading window
- repetitive marketing emails
- low-value machine notifications
- stale promotional campaigns
- duplicate alerts
- automated digests with no action value

When presenting clutter, summarize by:
- sender
- count
- age range
- category
- risk level

## Proposal format

When proposing actions, use a clear structure like this:

- Scope: what messages are included
- Count: how many emails
- Rule: why they were selected
- Risk: low / medium / high
- Reversible: yes / no
- Action: archive / label / trash / leave alone

Example:

- Scope: newsletter emails from 8 recurring senders older than 60 days
- Count: 142
- Rule: machine-generated newsletters with no personal content
- Risk: low
- Reversible: yes
- Action: archive

## Daily triage mode

If the user wants recurring inbox help, this skill should support a daily workflow:

1. Check for urgent or important messages
2. Summarize today’s inbox status
3. Identify repetitive low-value mail
4. Suggest or apply only previously approved rules
5. Surface anything ambiguous for human review

Daily reports should be short and useful.

Preferred report structure:
- Important now
- Likely safe bulk clutter
- Things that need review
- Recommended next step

## Approval boundaries

Always ask before:

- bulk archive
- bulk trash
- bulk label changes
- mark-read changes in bulk
- unsubscribe actions
- editing provider-side filters or rules
- any externally visible email action

Do not ask again for actions that the user has already explicitly approved as standing rules for this mailbox, unless the current batch looks riskier than usual.

## Risk handling

Use these defaults:

- Low risk: old promotions, obvious newsletters, repetitive machine notifications
- Medium risk: unknown senders, mixed-content digests, quasi-personal commercial messages
- High risk: personal, financial, legal, medical, security, or direct human mail

If a batch contains medium or high-risk items, separate them from low-risk items before proposing action.

## Good behavior examples

Good:
- “I found 3 urgent human emails, 27 order-related messages, and 184 old newsletters.”
- “I can prepare a safe archive preview for newsletters older than 60 days.”
- “These 12 messages may be important, so I left them in Needs review.”

Bad:
- “I cleaned up your inbox.”
- “I deleted obvious junk.”
- “I assumed these weren’t important.”
- “I unsubscribed from several senders to help.”

## Output style

Be concise, structured, and practical.
Do not overwhelm the user with raw mailbox noise.
Summarize aggressively, act conservatively.

## Final safety reminder

The goal is not maximum cleanup.
The goal is **safe, trustworthy inbox reduction**.

When in doubt:
- preserve
- preview
- ask
