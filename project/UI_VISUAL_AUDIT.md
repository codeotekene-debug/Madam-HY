# MADAM HY Smart Shop — Visual Audit Notes

**Audit date:** 2026-11-12  
**Environment:** Local Django app at `127.0.0.1:8000`; owner session used for management pages.  
**Evidence note:** Pages below were opened and reviewed through browser screenshots in the Codex in-app browser. The browser tool returned screenshots inline but exposes no supported local save path, so this audit does not claim a saved before/after image archive.

## Findings

| Page / area | Observed design weakness | Recommendation | Priority |
|---|---|---|---|
| Customer catalog and staff products | Several product images visibly depict unrelated content, including a computer login screen and a crest. This appears to be source product media, not a CSS crop problem. | Replace affected media with verified product photography; retain the branded fallback only for products without an image. | High |
| Customer product detail | Irrelevant product image and missing/short product descriptions weaken trust and make the detail view feel unfinished. | Correct product media and complete descriptions at the data/content level. | High |
| Customer order history on mobile | The table has an 800px minimum width and the surrounding layout previously allowed it to enlarge document width. | Constrain the page and panel; keep the table inside a horizontally scrollable, keyboard-accessible wrapper. | High |
| Customer order history | A loading message remained visible alongside rendered records during the earlier mobile review. | Ensure the loading state clears when data resolves and on request failures. | Medium |
| Owner dashboard | Sales chart has an empty grid without a helpful chart-specific empty state; product requests displayed stale “Demo data can be replaced…” copy. | Use truthful, consistent empty-state text and avoid demo/backend placeholder language. | Medium |
| Reports overview | Empty revenue chart is explicitly labeled, but a zero current period against a populated previous period reads as a raw -100% headline without enough context. | Add period labels and explain the comparison baseline; show “No current-period activity” as context while retaining the underlying financial values. | Medium |
| Growth report | The chart has sparse visual data with limited axis/context, making comparison difficult. | Use a labeled time-series chart with scale, period labels and a data table; show a useful empty state when no series exists. | Medium |
| Management Orders | Desktop filter controls are visually unbalanced: date/status/payment/sort controls occupy nearly all the row while search is narrow. | Group filters into a responsive grid with clear labels and consistent control widths. | Medium |
| Payments register | Long table presented as a very long page with no visible pagination in the reviewed screen. | Confirm pagination/row limit and provide compact filters plus clear pagination. | Medium |
| Customer / staff authentication | Empty error/alert region appeared as a blank pale-red strip in earlier sign-in screenshots. | Hide alert containers when empty and provide visible, associated validation feedback when populated. | Low |
| Rider and delivery management | Prior delivery acceptance notes report route success, responsive width, and no page JavaScript errors; the current browser audit session was pinned to the owner role and could not switch roles reliably. | Repeat a fresh rider/customer visual pass using isolated test sessions and persist screenshots when local capture is available. | Acceptance gap |

## Pages visually reviewed in this audit

- Customer storefront catalog, product detail, login, dashboard, orders, and cart (from the earlier visual pass in this task).
- Owner dashboard, reports overview, growth report, products, inventory, sales history, credits, expenses, orders, payments, POS, delivery dashboard/list/riders/zones/settings/reports, rider detail, notifications, activity logs, account profile, and Django administration (where available).
- Some management screens were reviewed at desktop size. Earlier customer captures included narrow mobile layouts; the owner account could not be switched to a customer or rider session for a complete current mobile-role acceptance pass.

## Changes from this pass

- Added width constraints to the customer order page, panel, and table wrapper so the table can scroll inside its container instead of widening its parent layout.
- Replaced stale owner dashboard demo-copy with a truthful no-recorded-information message.

## Acceptance gaps

- This audit did not save a complete screenshot archive; inline screenshots are not persisted files.
- Customer, rider, keyboard, form-feedback, and responsive verification still needs a stable role-switching browser session. No checkout, payment, delivery status, or configuration mutations were performed.
- Product photo and description problems require verified content updates, not cosmetic CSS changes.
