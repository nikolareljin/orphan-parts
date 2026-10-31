# Decide what it becomes

One place on the item's page that walks it through the question every orphan part raises: what
is it, what is it worth, what is it still good for, what would complete it, and so: keep it and
fix it, keep it and build, sell it, give it away, or let it go. The panel gathers what the other
panels already answered and adds two answers of its own: three scenarios written for you, and
ideas for what the item is good for. Nothing is decided for you; the choice is yours.

## Built so far

**Decide**, on the item's page below its values and details and above the other panels, starts
with one button, **What should I do with it?**, then six rows.

### What should I do with it?

The button has Muse Spark write three cards for this item and for you, side by side on a wide
screen and one above the other on a phone:

| Card | What it says |
|---|---|
| Keep and fix | the likely problem or problems behind the condition and faults you recorded (or that it works as it is), the repair steps written for your level, how hard that is for you (easy, moderate or hard) and why, naming the skill it rests on, the parts with a rough cost each, the total and the time; or that it is not worth fixing, and why |
| Reuse it | two or three things to make of it that fit your skills and tools, each naming the other items you own it would use (shown as the kinds you have now, without a count; a name that matches nothing you own is left out), how hard it is for you, the extra parts with their cost, and the time |
| Sell or give away | what makes it sellable as it stands and what listing and handing it over takes; the latest price guidance in a line when there is one, else **Get price guidance**, which asks the price route in your profile's currency (the scenarios themselves never price the item) |

Above the cards, one recommendation (keep and fix, reuse, sell or give away) with a one-line
reason tied to your profile; the recommended card is outlined. Each card has **Choose this**
(the sell card has **Sell it** and **Give it away**), which records the choice through the same
decision as the row below and takes you to the section that follows from it, moving the focus
there too. Each **Choose this** is named with its card for a screen reader (*Choose this: Keep
and fix*):

| Card | Choice recorded | Intent | Then |
|---|---|---|---|
| Keep and fix | `keep_fix` | keep | the repair steps, parts, cost and time are added to the item's notes (they stay private) and the page scrolls to the details, the focus in the notes |
| Reuse it | `keep_build` | build | the page scrolls to *What it is good for*, focused, with a link to [Build and reuse](reuse.md) |
| Sell or give away | `sell` or `give` | sell or give | the page scrolls to *Prepare to sell or give away*, focused on its heading; see [Seller flow](seller.md) |

The repair steps go into the notes only while the item is as it was when the cards were written,
checked in the same write as the notes. On cards that say *item changed since* the button reads
**Choose this (without the repair steps)**, with the hint *The item changed since; Ask again to
add the repair steps*: the choice is recorded and the notes stay as they are. When the notes and
the plan together would pass the notes' 4,000 characters, whole steps are left out from the end
and the plan ends with *… (more in the scenarios)*; the notes you wrote are never cut.

The cards are written for your [profile](profile.md): your rated skills, your tools, the effort
you will put in, whether you open devices up, and your budget. Without a profile they are
written for an average person with household tools, and the panel says so with a link to fill
one in. The brief holds the item's name and type, its condition, faults, tests done and
accessories, its intent so far, the values you accepted (never a serial number, a MAC address,
an IMEI or anything else that identifies the item or you), the profile, and the kinds of item
you own besides with how many of each (up to 40 kinds, nothing that is gone); never the
location, the notes, a photo, a price or a search. One structured call at low effort, about
1,200 tokens of answer.

The last cards are kept on the item with the item version they were written from, like the
ideas: they say *item changed since* once the item is edited or decided, and **Ask again** writes
a new version. The demo visitor is refused, as on every other call that spends.

### The rows

| Row | What it shows | Who answers |
|---|---|---|
| What it is | the kind of item and how many of its values you have accepted, with a link down to the values | the inventory |
| What it is worth | the latest price guidance in a line: the typical asking figure (the estimate's when nothing was asked), the strategy to start from, weak evidence and *item changed since* when either applies; **Ask what it is worth**, shown when none was made, takes you to the Value panel's form, where the currency and the place are yours to give; the row reads the new guidance as soon as the panel writes it | Muse Spark proposes, the rules keep what a page backs; see [Value an item](value.md) |
| What it is good for | the project templates in the catalog with a requirement this kind of item fills, named with the requirement; then **Ask for ideas** | the templates are the rules, from the item's type against each requirement's kinds; the ideas are the model's proposals and the panel says so |
| What would complete it | the open searches from this item with their candidate counts, the Marketplace search to run, and a link to [Find a part](search.md) | the inventory |
| What it could look like | a link to the picture controls | draw on request when enabled |
| Decision | **Keep and fix**, **Keep and build**, **Sell**, **Give away**, **Not worth it**, with a note; an item a selected project counts on says so first: *Reserved by <project>: selling or giving it away breaks that build* | you |

**Ask for ideas** has Muse Spark propose up to three uses for the item: a title, what it would
do, what else it needs that the item does not bring, the effort (low, medium or high) for a
person with your skills, and one thing to check first. The brief it is given holds the item's
accepted values, its condition, faults and tests done, your [preferences](reuse.md) (interests,
skills, budget) and the templates the rules already found it fills; nothing else. The answer is
kept on the item with the item version it was written from, says *item changed since* once the
item is edited (including while the request is running), and is shown under the heading *The model's proposals*, because that is what it
is: the rules did not check it, and a part the tests do not call working is not working because
an idea assumes it.

The decision sets the item's intent (**Keep and fix** to *keep*, **Keep and build** to *build*,
**Sell** and **Give away** to the same, **Not worth it** to *keep*, with the note saying why)
and writes
`decided: <choice>: <note>` into the item's history, so the why is kept beside the what. The
version is bumped when the intent changes, a note is given, or the notes gain the repair steps; the same choice said again with
nothing added is a line in the history and nothing more, so a guidance or an idea written before
it stays current. **Sell** and **Give away** scroll to *Prepare to sell or give away* with the
mode set; see [Seller flow](seller.md). The panel shows the last decision with its date.

The decision is yours even when a selected, building or done project counts on the item: the
panel names the project above the buttons and does not stop you. A refused decision (the demo
visitor, an item changed meanwhile, no connection) is said under the buttons and the note stays
as typed; nothing scrolls, because nothing was decided. The choice carries the item version the
panel showed: if the item changed in another tab since, the choice is refused, the item is
reloaded, and you choose again from what it is now.

Everything on the panel is behind the access code: the demo visitor sees the demo line in its place.

## Next

The picture controls draw an illustration on request with Muse Image when enabled. The other rows follow what their own panels learn:
a search that finds its candidate counts here, a guidance redone after the item changed says so.

On a phone, the row labels sit above their answers so the panel fits the dialog.
