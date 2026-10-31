# Profile

What you can do and what you have, kept once for the inventory. The scenarios on an item
([Decide what it becomes](decide.md)) are written for it, and so are the build proposals
([Build and reuse](reuse.md)).

## Built so far

**Profile**, in the header, is one form:

- **Skills**, each rated *none*, *some*, *confident* or *pro*. Ten are always listed: software,
  electronics and soldering, woodworking, metalwork, handcrafting and sewing, plumbing, 3D
  printing, arts and crafts, car and mechanics, home repair. **Another skill** adds one of your
  own with its level; a skill of your own can be removed, the listed ones stay at *none*.
- **Tools I have**, in a line.
- **Effort I will put in**: an hour or so, an afternoon, or a weekend or more.
- **I open devices up**.
- **Budget**, **Currency** and **Radius (km)**.

**Save profile** keeps it. The record is the one behind `GET /api/preferences` and
`PUT /api/preferences`; the Build page's form edits its interests and the way you buy (used,
new or either) and shows the rated skills in a line with a link here.

**Ratings and older records.** The skills are a list of `{skill, level}`. A record saved before
the ratings held plain names; it is read as it is stored, and each plain name reads as *some*.
The record is written in the rated shape the next time it is saved. `PUT /api/preferences`
takes either shape: a plain name in a request is a skill at *some*. A blank name is dropped and
a name given twice keeps its first rating.

**How the scenarios use it.** The brief names every rated skill with its level, the tools, the
effort in words, whether you open devices up and the budget. Each card says how hard the work
is for you and names the skill that makes it so; a repair that needs plumbing is *hard* when
plumbing is *none*. Without a saved profile the cards are written for an average person with
household tools and the panel says so.

The profile is behind the access code; the demo visitor sees the demo line in its place.
