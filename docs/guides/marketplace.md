# Marketplace handoff

The draft is shaped to the Marketplace create-item fields. Open in Marketplace copies the draft and opens the create page; posting stays a manual step. No automation of facebook.com.

## Built so far

No public API posts a personal Marketplace listing, and automating the site is against its
terms, so the handoff stops at the create page. From an item's page, **Write the draft**
produces the title, price, category, condition, description, tags and photo order (see the
[seller flow](seller.md)); each has its own **Copy** button, **Download photos** zips the photos
in that order, and **Open Marketplace** opens the create-item page in a new tab. Posting is
yours: nothing is sent to facebook.com by the service, and the draft is not changed on the way.
The page is `MARKETPLACE_CREATE_URL`. **Mark as listed**, **Mark as sold** and **Mark as given**
record what happened after.
The other way round, **Search Marketplace** on a [search request](search.md) opens the search
page with the request's words and top price (`MARKETPLACE_SEARCH_URL`); you run it and bring a
listing back.
