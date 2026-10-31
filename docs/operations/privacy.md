# Privacy

## What is kept, and where

- Photos are stripped of EXIF and GPS metadata on ingest, before anything else happens; the
  phone re-encodes its photos before they leave it, so only pixels are sent.
- A photo sent for a reading is read in memory and dropped with the request. When you save the
  item, the web form keeps those photos with it under `DATA_DIR/items/`, and an item read from a
  capture keeps the capture's photos the same way; they go when you delete the item. The photo a
  measurement was made on is kept, with the measurement, on the item.
- A capture from the phone (photos, clip, note) is kept under `DATA_DIR/captures/` until you
  delete it from the Inbox; the clip as the phone wrote it, its own metadata included.
- A picture drawn with **Draw it** is kept with the item, the set of decision cards or the
  project it was drawn for, captioned as drawn, and goes with it.
- The phone app keeps the backend URL, the access code (or the label and expiry of the code it
  was issued) and a session token in its private storage.
- Nothing is purged on a timer: `RETENTION_HOURS` has no job behind it yet. What is kept is
  listed above, and goes when you delete it.

## What leaves the machine

Only these, and only to the Meta Model API, each when you ask for it:

| Call | What is sent |
|---|---|
| Reading a label | the photos, re-encoded, and the label crops SAM 3.1 found |
| Reading a capture | its photos and its spoken note; never the clip |
| A voice note | the recording |
| A listing brought back | its text or the screenshot |
| A listing draft | the accepted values (none that identifies the item: a serial number, MAC address or IMEI stays out), the public listing details (condition, faults, what was not tested, what is included, the data line, handover, area, availability) and the item's first four photos at 768 px; never the lowest price you would take or your reason for selling |
| Price guidance | the same values and details, the currency and the place you give, which the Model API also turns into web searches |
| The search plan | the need's title, profile and needed values, the values of the item that needs it, the search's notes and its top price |
| The decision cards | the item's name and type, condition, faults, tests, accessories, intent and accepted values; your profile (rated skills, tools, effort, whether you open devices up, budget); the kinds of item you own besides, with how many of each; never the location, the notes, a serial number, a photo, a price or a search |
| What it is good for | the item's details and accepted values, your interests, skills and budget, and the labels of the templates it fills; never the location, the notes, a serial number, a photo or a search |
| Build proposals | your preferences and, through the tools the model calls, the items a build may use with their fields, condition, faults, tests, accessories and parts |
| **Draw it** | for an item, its type, up to eight accepted values (none that identifies it), its condition and faults and the use you typed; for a decision card or a project, its title, what it does and the kinds of the items it uses with up to three accepted values each; never a name, the location, the notes, a price or a photo |

The build pack, the outcome and its share text are written by the rules on this machine and
sent nowhere. The phone app sends to your backend and nowhere else. A listing's link is kept as
you gave it and never opened. Nothing is posted, searched or fetched on Marketplace for you.

## Sessions and codes

With an access code set, the browser keeps one session cookie that holds no account and nothing
about you; it ends after `DEMO_SESSION_HOURS` or when you sign out. Codes issued with
`./dev keys`, and the phone codes a scan of the pairing QR issues, are kept as hashes with a
label; the log notes the label when a session opens, never the code. The QR code never carries
the access code.

## What a visitor without the code sees

Without the code a visitor is the demo. They read the demo set's own photos, picked in a
gallery, and each answer is a recording: nothing they do is sent to the Model API, and there is
no upload to send. Items are private unless the owner marks one public (the demo set loads as
public); of a public item the visitor sees its values, photos and drawn pictures, and never:

- where it is kept, its notes, a voice note or a clip;
- a draft, the listing details, price guidance, a decision or its cards;
- the searches, the listings brought back, the candidates, the projects, the profile, or a
  capture that is not public.

No accounts, no tracking, no third-party scripts in the web app.
