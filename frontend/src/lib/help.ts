// The short notes behind the "?" buttons: what can be done at that spot and how, in a sentence
// or three, and the page of the docs that says more. Each topic names the button
// ("Help: <topic>"), so it is worded apart from the page's other buttons and labels.

export const DOCS_BASE = 'https://nikolareljin.github.io/orphan-parts/'

export type HelpEntry = { topic: string; text: string; doc?: string }

export function docsUrl(doc: string): string {
  return DOCS_BASE + doc
}

export type HelpAction = 'toggle' | 'escape' | 'outside' | 'close'

// Whether the note is open after an action: the "?" toggles it, everything else closes it.
export function helpNext(open: boolean, action: HelpAction): boolean {
  return action === 'toggle' ? !open : false
}

export const HELP = {
  signIn: {
    topic: 'signing in',
    text:
      'Without the code you are in the demo: you can open the public items and read the sample photos, with recorded answers, and nothing is saved. ' +
      'The access code unlocks your own photos, saving, drafts, prices, projects and captures, and the live models when this server has a key.',
    doc: 'start/demo/#without-the-code',
  },
  read: {
    topic: 'label photos',
    text:
      'Choose photos of one label, sharp and straight on, and press Read the label. Muse Spark reads each value with its confidence and where it was read. ' +
      'Name it and Save privately: it goes to My inventory, where each value waits for you to confirm it.',
    doc: 'guides/capture/#on-the-computer',
  },
  readSamples: {
    topic: 'label photos',
    text:
      'Pick photos from the demo set and press Read the label. Each reading is the one recorded for that photo, so nothing is spent and nothing is kept. ' +
      'Sign in with the code to read your own photos.',
    doc: 'start/demo/#without-the-code',
  },
  findFirst: {
    topic: 'SAM 3.1 regions',
    text:
      'SAM 3.1 first looks for the item, the label and the connector, and Muse Spark reads the regions it found along with the photo. ' +
      'Where it finds none, the whole photo is read. Leave it on for busy photos.',
    doc: 'guides/capture/#on-the-computer',
  },
  inbox: {
    topic: 'phone captures',
    text:
      'Captures from the phone app, or sent from this computer with the form above, wait here unread; nothing is spent until you press Read it. ' +
      'Read it turns one into an item: Muse Spark reads the label (SAM 3.1 finds it first when the capture asked for that) and Muse Voice Transcribe writes down the voice note. Then Open item shows it.',
    doc: 'guides/capture/#in-the-inbox',
  },
  inboxDemo: {
    topic: 'phone captures',
    text:
      'Captures come from the paired phone app: photos, a short video, a voice note and a line of text. ' +
      'Without the code only the captures shown in the public demo are listed, and nothing can be sent.',
    doc: 'guides/capture/',
  },
  inventory: {
    topic: 'item list columns',
    text:
      'Plan is the last choice made under Decide, or what the item is meant for. Saved results lists the answers kept with it (cards, ideas, drafts, price guidance); ' +
      'opening them again asks no model. Open shows the whole item.',
    doc: 'guides/inventory/',
  },
  inventoryDemo: {
    topic: 'item list columns',
    text:
      'The demo set’s public items, read-only. Plan is the choice made for each, or what it is meant for; Saved results lists what was asked for it, shown as it was saved. ' +
      'Open shows the whole item.',
    doc: 'start/demo/#without-the-code',
  },
  facts: {
    topic: 'confirming what was read',
    text:
      'Values read from the photos wait as to confirm: Accept or Reject each one, checking it against the photos. ' +
      'Known from says where a value came from: a photo (with its confidence), your word, documentation, a test or an estimate. Add what you know adds one yourself.',
    doc: 'guides/inventory/#step-by-step',
  },
  factsVisitor: {
    topic: 'confirming what was read',
    text:
      'The values known about this item, read-only. Known from says where each came from: a photo (with its confidence), the owner’s word, documentation, a test or an estimate. ' +
      'Values the owner has not checked yet are marked to confirm.',
    doc: 'guides/inventory/#step-by-step',
  },
  photos: {
    topic: 'hidden areas on photos',
    text:
      'Each photo is checked once, when it is kept, for things like product keys, MAC addresses, passwords and serial numbers. ' +
      'Those areas are blacked out on every copy that leaves your view. Click a photo to see them outlined, and Show or Hide each one.',
    doc: 'guides/private-details/',
  },
  photosVisitor: {
    topic: 'hidden areas on photos',
    text:
      'Each photo was checked when it was kept for things like product keys, MAC addresses, passwords and serial numbers. ' +
      'The photos you see are copies with those areas blacked out; the notes above say what was found. Only the owner sees the originals and chooses what stays hidden.',
    doc: 'guides/private-details/',
  },
  publicDemo: {
    topic: 'public demo',
    text:
      'Ticked, visitors without the access code can open this item read-only: its values, its photos with private details blacked out, and its drawings. ' +
      'Where it is kept and your notes stay private.',
    doc: 'start/demo/#without-the-code',
  },
  decide: {
    topic: 'scenario cards',
    text:
      'One Muse Spark call writes three cards for you (keep and fix, reuse, sell or give away) and recommends one; the button on a card records your choice on the item. ' +
      'Ask again adds new cards and keeps the earlier ones a click away. Opening this section asks no model.',
    doc: 'guides/decide/',
  },
  decideVisitor: {
    topic: 'scenario cards',
    text:
      'The three cards (keep and fix, reuse, sell or give away) and the recommendation, as Muse Spark wrote them for the owner, with any earlier cards a click away. ' +
      'Reading them asks no model. Sign in with the code to ask for cards or record a choice.',
    doc: 'guides/decide/',
  },
  value: {
    topic: 'price figures',
    text:
      'Get price guidance is one Muse Spark call with web search. Four figures stay apart: asking prices seen, sold prices seen, sales you reported and the model’s estimate, ' +
      'each with its sources and dates, and weak evidence is said. You set the price.',
    doc: 'guides/value/',
  },
  valueVisitor: {
    topic: 'price figures',
    text:
      'The price guidance the owner asked for, shown as it was saved. Four figures stay apart: asking prices seen, sold prices seen, the owner’s own sales (kept private) and the model’s estimate, ' +
      'each with its sources and dates. Sign in with the code to ask for guidance.',
    doc: 'guides/value/',
  },
  sell: {
    topic: 'posting on Marketplace',
    text:
      'Write the draft has Muse Spark write the listing in Marketplace’s fields, for you to copy. Nothing is posted for you: ' +
      'Open Marketplace opens the create page, and you paste the fields and post it yourself.',
    doc: 'guides/marketplace/',
  },
  sellVisitor: {
    topic: 'posting on Marketplace',
    text:
      'The listing draft the owner had Muse Spark write, if there is one, read-only. The app never posts on Marketplace: the owner pastes the fields and posts it. ' +
      'Sign in with the code to write a draft.',
    doc: 'guides/marketplace/',
  },
  measure: {
    topic: 'measuring from a photo',
    text:
      'Use a photo with a ruler or a card in it: click the two ends of the known length, then the two ends of the feature. ' +
      'The size is geometry from your marks, no model, and comes with its uncertainty; a photo that cannot carry a number is refused with the check that failed.',
    doc: 'guides/measure/',
  },
  picture: {
    topic: 'drawn pictures',
    text:
      'Draw it has Muse Image draw what the item could become, or the item itself if the line is left blank; each click is one paid call. ' +
      'Pictures are labeled as drawn and never count as evidence about the item.',
    doc: 'models/muse-image/',
  },
  pictureVisitor: {
    topic: 'drawn pictures',
    text:
      'What Muse Image drew for the owner: what the item could become, or the item itself. ' +
      'Pictures are labeled as drawn and never count as evidence about the item.',
    doc: 'models/muse-image/',
  },
  find: {
    topic: 'part searches',
    text:
      'Each search is a part you need, run on Marketplace by you: the app builds the links and reads what you bring back, but never searches, fetches or posts on Marketplace. ' +
      'Open a search to plan it, search the web and check listings for fit.',
    doc: 'guides/search/',
  },
  findDemo: {
    topic: 'part searches',
    text:
      'The searches made for the demo set’s public items, read-only: the plan, the listings brought back and the candidates with their verdicts. ' +
      'Sign in with the code to start, plan or search.',
    doc: 'guides/search/#without-the-access-code',
  },
  newSearch: {
    topic: 'starting a search',
    text:
      'Pick the item that needs the part (its values become what is needed), or a profile and the values you type. ' +
      'Add a max price, then Start the search; no model call.',
    doc: 'guides/search/#step-by-step',
  },
  plan: {
    topic: 'search plan',
    text:
      'Plan the search is one Muse Spark call: a few phrasings, each a Marketplace link with your max price, and a match pattern with words that rule a listing out. ' +
      'You open the links and run the searches yourself.',
    doc: 'guides/search/#plan-the-search',
  },
  planVisitor: {
    topic: 'search plan',
    text:
      'The plan Muse Spark wrote for this search: a few phrasings, each a Marketplace link with the max price, and a match pattern with words that rule a listing out. ' +
      'Sign in with the code to plan a search.',
    doc: 'guides/search/#plan-the-search',
  },
  web: {
    topic: 'web search',
    text:
      'Search the web is one Muse Spark call with web search. Only pages a search result actually returned are kept, each with its link, and they join the listings below. ' +
      'Marketplace itself is not searched.',
    doc: 'guides/search/#search-the-web',
  },
  bringBack: {
    topic: 'scoring and fit',
    text:
      'Paste listings you found (separated by --- or a blank line), or add screenshots for Muse Spark to read, one call each; all are ranked by the pattern, the words to skip and the price, with no model call. ' +
      'Check fit reads one listing with Muse Spark, then the profile’s rules decide; what is unknown becomes a question for the seller.',
    doc: 'guides/match/',
  },
  bringBackVisitor: {
    topic: 'scoring and fit',
    text:
      'The listings the owner brought back, ranked by the pattern, the words to skip and the price, and the fit checked for some of them; what is unknown became a question for the seller. ' +
      'Sign in with the code to bring back listings or check fit.',
    doc: 'guides/match/',
  },
  buildPrefs: {
    topic: 'build wishes',
    text: 'Your interests, effort, budget and how you buy parts, saved once; the skills come from your Profile. Every proposal is written for them.',
    doc: 'guides/reuse/#step-by-step',
  },
  buildPrefsVisitor: {
    topic: 'build wishes',
    text: 'The owner’s interests, effort and skills, read-only. Every proposal below was written for them.',
    doc: 'guides/reuse/#step-by-step',
  },
  propose: {
    topic: 'proposals',
    text:
      'Propose asks Muse Spark for builds from your inventory and the project templates; only ideas that use items you own are kept. ' +
      'Open one to see what it uses, what is still missing and the steps.',
    doc: 'guides/reuse/#step-by-step',
  },
  proposeVisitor: {
    topic: 'proposals',
    text:
      'Builds Muse Spark proposed from the owner’s inventory and the project templates, read-only. ' +
      'Open one to see what it uses, what is still missing and the steps. Sign in with the code to ask for proposals.',
    doc: 'guides/reuse/#step-by-step',
  },
  project: {
    topic: 'selecting a project',
    text:
      'Select and commit the items reserves your items for this build, and the steps become a checklist. Draw it has Muse Image draw how the finished build could look, labeled as drawn. ' +
      'The build pack is one document written from your data, with no model call.',
    doc: 'guides/reuse/#step-by-step',
  },
  projectVisitor: {
    topic: 'selecting a project',
    text:
      'A build the owner planned, read-only: the items it uses, the steps and, once written, the build pack (one document from the owner’s data, no model call). ' +
      'Sign in with the code to select, commit or draw a build.',
    doc: 'guides/reuse/#step-by-step',
  },
  stillNeeded: {
    topic: 'missing parts',
    text:
      'Find it on Marketplace opens a search for the missing part on Find a part, with the budget left as its top price. ' +
      'Or fill it with one of your own items: pick it and Use it.',
    doc: 'guides/reuse/#step-by-step',
  },
  stillNeededVisitor: {
    topic: 'missing parts',
    text:
      'What this build still lacks. The owner fills a gap with a part found on Marketplace or with one of their own items; sign in with the code to do the same.',
    doc: 'guides/reuse/#step-by-step',
  },
  skills: {
    topic: 'rating skills',
    text:
      'Rate what you can do: none, some, confident or pro. The Decide cards and the build proposals are written for these levels, your tools and the effort you will put in.',
    doc: 'guides/profile/',
  },
  skillsVisitor: {
    topic: 'rating skills',
    text:
      'The owner’s skills, each rated none, some, confident or pro, read-only. The Decide cards and the build proposals are written for these levels.',
    doc: 'guides/profile/',
  },
  pair: {
    topic: 'phone pairing',
    text:
      'Install the Android app first (the install code), then pair it: open the connect code, then on the app’s Backend tab tap Scan to pair. ' +
      'Signed in, the connect code also gives the phone an access code of its own.',
    doc: 'start/pairing/',
  },
  feedback: {
    topic: 'like and dislike',
    text:
      'Like what came out right, dislike what came out wrong, and say what is wrong in one line if you like; a second click takes the vote back. ' +
      'Your dislike of a drawing steers your next drawing of the same thing, which avoids what you said is wrong (another composition, with no reason) and says so in its caption. ' +
      'The picture and recommendation reviews also read the dislikes as flagged by a person and keep the liked ones as they are.',
    doc: 'guides/picture-review/#peoples-votes',
  },
} satisfies Record<string, HelpEntry>
