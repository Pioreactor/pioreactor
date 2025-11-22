# Pioreactor Frontend Design Notes

## Theme and layout
- **Theme provider**: Material UI theme sets a light background (`#f6f6f7`) with a purple primary (`#5331CA`) and a red secondary (`#DF1A0C`).
- **Shell**: Global `CssBaseline` with a fixed top app bar and a 230px left drawer (`react-pro-sidebar` + MUI `Drawer`) to anchor navigation, leaving the main content padded via theme spacing.

## Typography
- **Sans stack**: Body font stack prioritizes platform sans fonts with Roboto available; Roboto weights 400/500/700 are preloaded.
- **Monospace**: Code blocks use the `source-code-pro` stack.
- **Casing**: Buttons keep natural casing (`text-transform: none`) globally.

## Color system
- **Primary palette**: Primary purple (`#5331CA`) and secondary red (`#DF1A0C`) applied across navigation, actions, and badges.
- **Surface**: Light gray page background (`#f6f6f7`) for overall canvas.
- **Status tokens**: Ready/active green (`#176114`), disconnected gray (`#585858`), lost red (`#DE3618`), inactive gray (`#99999b`), plus optional backgrounds (`#DDFFDC` for “ready” states).
- **Alerts**: Error (`#FF8F7B`), warning (`#ffefa4`), and notice (`#addcaf`) fills.
- **Data series**: Shared `colors` array provides a 24-color cycle for charts/series (blues, teals, oranges, purples, greens) via `ColorCycler`.

## UI accents and microinteractions
- **Editable affordance**: `contenteditable` paragraphs gain a `#51a7e8` border on hover with subtle rounding.
- **Indicators**: Default indicator dots use a pink glow (`#ea4c89` with inset shadow); LAP online indicator swaps to a green glow (`#2FBB39`).
- **Underlines**: Dotted underline (`rgba(0, 0, 0, 0.87)`) class for emphasis without full text decoration.
- **Attention**: Blink keyframes for LED/icons provide short attention-grabbing flashes on status changes.
