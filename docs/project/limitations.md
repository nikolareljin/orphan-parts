# Limitations

- Two deep categories (power adapters, vacuum attachments). Other parts go through the generic
  profile until a profile exists for them.
- The app reads what is on the label or in a listing. A wrong or counterfeit label gives wrong
  fields; a seller's text is read as written, and only values a page backs count as comparables.
- A dimension needs a reference in the same plane; the uncertainty reported is a bound derived
  from the marks and the reference, not a measurement of the error. A dimension match filters
  candidates and never proves a fit on its own.
- Searching and posting on Marketplace stay yours. There is no public listing API for
  individuals; the app hands off a search and a create page and never automates facebook.com.
- Verdicts are only as good as the evidence. A listing that states nothing ends in
  `INSUFFICIENT_INFO`; a candidate's observation is trusted for a limited time.
- The demo's allowances and counts live in one process and start over with it; the spend cap on
  disk is the floor.
- Human review is required before anything is posted, bought or sold.
