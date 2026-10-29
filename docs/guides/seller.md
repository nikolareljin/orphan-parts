# Seller flow

Photos in, listing draft out: upload, segmentation overlays, evidence table, voice note, questions to resolve, copy or hand off to Marketplace.

## Built so far

Up to four photos go in. With "Find the label first" on, SAM 3.1 finds the item, the label
and the connector in the first photo; the overlay and the crops are shown, and the label crop
goes to Muse Spark with the photos, so every value is sourced `label_crop`. When the label
cannot be found first, the photos are read whole and the page says why. The evidence table
shows every field read with its value, unit, confidence, source and the text as printed, the
warnings, the label transcription, the model and the cost of the calls. The rest of the flow
follows.
