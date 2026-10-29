# Marketplace handoff

The draft is shaped to the Marketplace create-item fields. Open in Marketplace copies the draft and opens the create page; posting stays a manual step. No automation of facebook.com.

## Built so far

From an item's page, **Write the draft** produces the title and the text (see the
[seller flow](seller.md)); **Copy the draft** puts both on the clipboard and **Open Marketplace**
opens the create-item page in a new tab. Posting is yours: nothing is sent to facebook.com by
the service, and the draft is not changed on the way. The page is `MARKETPLACE_CREATE_URL`.
The other way round, **Search Marketplace** on a [search request](search.md) opens the search
page with the request's words and top price (`MARKETPLACE_SEARCH_URL`); you run it and bring a
listing back.
