# Palette and type

Every color is taken from `logo.svg`; nothing is added. The logo itself is never recolored,
cropped or redrawn: the cards and overlays link to the file and place it whole.

| Name | Hex | From the logo | Use |
|---|---|---|---|
| Ink | `#0e131d` | tile gradient, bottom | title panels, card base |
| Night | `#1b2436` | tile gradient, top | boxes on cards and diagrams |
| Line | `#2d384d` | tile border | panel borders, rules |
| Mist | `#94a3b8` | prong gradient | secondary text, footers |
| Silver | `#cbd5e1` | prong gradient | body text on dark, the logo plate |
| Paper | `#f8fafc` | prong gradient | titles |
| Teal | `#00f5d4` | ring and loop | the one accent: title rule, *in the app* titles, data lines |
| Sky | `#00bbf9` | loop | recorded answers, sample data, video lines |
| Violet | `#7b2cbf` | loop | the *planned* border on the models card; never text |
| Magenta | `#d946ef` | loop | *concept preview* only, power lines, missing parts |

Card backgrounds run from `#121a28` to `#0a0e15`, a shade either side of Ink, so the logo's
own tile and its border stay visible.

Contrast on Ink: Paper 17.8:1, Silver 12.5:1, Teal 13.3:1, Sky 8.4:1, Mist 7.3:1, Magenta
5.4:1, all above WCAG AA for text. Violet is 2.6:1, so it is a border color only, never text.

## Type

Noto Sans (SIL Open Font License 1.1), the same in both videos:

- card title: 96 to 104 px, weight 600, Paper, a 120 x 6 px Teal rule under it
- title panel: badge 20 px weight 700 tracked 2 px in the kind's color; title 44 px weight
  600 Paper; line 28 px Silver
- captions: the editor's plain sans at about 44 px, white on a 60 percent black box,
  bottom center, two lines at most

Clipchamp and Kdenlive do not need the font: the cards and titles are pictures. If a title
has to be typed in the editor, use its plainest sans (Clipchamp: *Noto Sans* when listed,
otherwise *Arial*) at the sizes above.

## Placement

- Corner logo: top right, 112 px, 64 px from the top and right edges
  (`corner-overlay.png`). On dark footage use `corner-overlay-plate.png`, the same logo on a
  Silver plate.
- Titles: top left, 96 px from the left, 72 px from the top.
- Captions: bottom center. Nothing else in the bottom 200 px.

## The logo plate

`logo-plate.png` puts the logo on a Silver rounded plate. Use it only where the logo's dark
tile would sink into dark footage. It is never needed on the cards.
