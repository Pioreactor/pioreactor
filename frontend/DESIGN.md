# Pioreactor Frontend Design Guidelines

This is the canonical visual and interaction design reference for the Pioreactor
frontend. It applies to route pages and shared components under `frontend/src/`.

The existing UI is evidence for these rules, but it is not automatically the
authority. Where the frontend currently uses several patterns for the same
thing, this document chooses one pattern and records the drift under
[Known inconsistencies](#known-inconsistencies).

## Rule language

- **Must** means new work should follow the rule.
- **Should** means follow the rule unless the feature has a concrete reason not
  to.
- **May** means the pattern is optional and context dependent.

## Design intent

The Pioreactor UI is an operational interface. It should feel calm, legible,
and predictable while still fitting useful information on screen.

1. The same meaning must use the same visual treatment.
2. Controls must look different from labels.
3. Interactive rows must look and behave differently from scan-only rows.
4. Status must never be communicated by color alone.
5. User actions must produce immediate visible feedback.
6. Dense information is acceptable; ambiguous information is not.

## Foundations

### Color

Use theme tokens where they exist. The values below define the intended visual
result and should be moved into the theme as repeated patterns are consolidated.

| Purpose | Value | Usage |
| --- | --- | --- |
| Page background | `#F6F6F7` | App canvas behind cards and content |
| Surface | `#FFFFFF` | Cards, table heads, controls |
| Zebra row | `#F7F7F7` | Odd rows in non-clickable tables and lists |
| Primary | `#5331CA` | Primary actions, links, focus, active navigation |
| Primary tint | `#5331CA14` | Selected navigation and low-emphasis selection |
| Destructive | `#DF1A0C` | Delete, stop, remove, and destructive text/actions |
| Primary text | `rgba(0, 0, 0, 0.87)` | Main text |
| Secondary text | `rgba(0, 0, 0, 0.60)` | Supporting metadata |
| Disabled text | `rgba(0, 0, 0, 0.38)` | Disabled state |
| Ready | `#176114` | Ready/on/active state, with text or an icon |
| Ready background | `#DDFFDC` | Ready/on status surface |
| Disconnected | `#585858` | Off/disconnected state |
| Lost | `#DE3618` | Lost/unreachable state |
| Inactive | `#99999B` | Inactive state |
| Error log fill | `#FF8F7B` | Error log rows or cells |
| Warning log fill | `#FFEFA4` | Warning log rows or cells |
| Notice log fill | `#ADDCAF` | Notice log rows or cells |

Do not introduce another near-white table color. The two table row colors are
exactly:

```text
Odd row:  #F7F7F7
Even row: #FFFFFF
```

### Typography

- A route page must have exactly one semantic `h1`.
- The page title uses MUI `Typography` with `variant="h5"`, `component="h1"`,
  and bold weight.
- A major section uses `variant="h6"` and `component="h2"`.
- Smaller nested headings should continue the semantic order rather than
  choosing a heading level for its default size.
- Supporting metadata uses `body2` or `subtitle2` with `text.secondary`.
- Button and navigation labels use sentence case. Do not uppercase labels.
- A heading contains text, not form controls. Filters and selectors belong
  below the heading or in an adjacent toolbar.

### Spacing

- Use MUI theme spacing in `sx` for layout. Prefer `1`, `1.5`, `2`, `3`, and
  `4` over one-off pixel values.
- The app shell owns the outer page gutters. Route pages must not add a second
  outer left or right margin.
- Use `16px` (`2` theme units) between major page regions.
- Use `8px` (`1` theme unit) between a title row and its divider.
- Fixed pixel values are acceptable when they describe a physical visual
  detail, such as a 1px border or a compact icon size.

## Page structure

The normal page order is:

1. Page header
2. Divider
3. Optional page-level explanation, status, or filters
4. Primary content
5. Optional documentation link or secondary help

Do not put the page title inside a `Card`. Cards contain page content; they do
not replace the page header.

### Page headers

There are three approved page header variants.

#### 1. Title and actions

Use this for collection, administration, and operational pages with actions.
Examples include Inventory, Pioreactors, Updates, and Export data.

```jsx
<Box component="header" sx={{ mb: 2 }}>
  <Box
    sx={{
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      gap: 2,
      flexWrap: "wrap",
      mb: 1,
    }}
  >
    <Typography variant="h5" component="h1" sx={{ fontWeight: "bold" }}>
      Inventory
    </Typography>
    <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
      {actions}
    </Box>
  </Box>
  <Divider />
</Box>
```

Rules:

- The title is on the left and actions are on the right.
- Actions may wrap below the title on narrow screens.
- The header always ends with a horizontal divider.
- Use a vertical divider only to separate meaningfully different action
  groups, such as normal actions from destructive or overflow actions.
- Keep the primary page action closest to the title-side of the action group.

#### 2. Title only

Use this when a page has no page-level actions.

```jsx
<Box component="header" sx={{ mb: 2 }}>
  <Typography variant="h5" component="h1" sx={{ fontWeight: "bold", mb: 1 }}>
    Protocols
  </Typography>
  <Divider />
</Box>
```

Do not omit the divider merely because the action group is empty.

#### 3. Detail page

Use this for a single calibration, estimator, Pioreactor, profile, or other
named record.

```jsx
<Box component="header" sx={{ mb: 2 }}>
  <Box
    sx={{
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      gap: 2,
      flexWrap: "wrap",
      mb: 1,
    }}
  >
    <Button component={Link} to="/calibrations" startIcon={<ArrowBackIcon />}>
      All calibrations
    </Button>
    <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
      {actions}
    </Box>
  </Box>
  <Divider />
</Box>
<Box sx={{ mb: 2 }}>
  <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
    <Typography variant="h5" component="h1" sx={{ fontWeight: "bold" }}>
      Calibration: media-pump-1
    </Typography>
    {status}
  </Box>
  <Typography variant="subtitle2" color="text.secondary">
    {parentMetadata}
  </Typography>
</Box>
```

Rules:

- A back link is navigation. It must not be the page's `h1`.
- Back-navigation Buttons use `startIcon={<ArrowBackIcon />}`. Do not render
  `ArrowBackIcon` as a child or add manual icon sizing, margins, or alignment.
- The back link and page actions share a toolbar above the divider.
- The divider sits directly beneath that toolbar so its position does not
  change with the record title, status, or parent metadata.
- The record name is the `h1`.
- A short status chip may sit beside the title.
- The record title, status, and parent metadata appear below the divider.
- Breadcrumbs or parent metadata use links and text, not Chips.

### Header filters

Filters, target selectors, search, and sorting controls belong in one of these
locations:

- A compact toolbar or `Card` immediately below the page header.
- A section toolbar immediately above the content they affect.

Do not embed `Select`, `Autocomplete`, or other form controls inside the page
title. The title must remain a stable description of the route.

## Entity labels and Chips

Use a small MUI `Chip` when a named domain entity appears in page content. The
icon makes the entity type recognizable and the Chip separates an identifier
from surrounding prose.

| Entity | Icon |
| --- | --- |
| Pioreactor | `PioreactorIcon` |
| All/multiple Pioreactors | `PioreactorsIcon` |
| Experiment | `PlayCircleOutlinedIcon` |
| Calibration | `TuneIcon` |
| Estimator | `EstimatorIcon` |
| Experiment profile | `ViewTimelineOutlinedIcon` |

Standard Pioreactor label:

```jsx
<Chip
  size="small"
  icon={<PioreactorIcon />}
  label={pioreactorUnit}
  data-pioreactor-unit={pioreactorUnit}
/>
```

When the entity navigates somewhere, the Chip itself should be the link:

```jsx
<Chip
  size="small"
  icon={<PioreactorIcon />}
  label={pioreactorUnit}
  clickable
  component={Link}
  to={`/pioreactors/${pioreactorUnit}`}
  data-pioreactor-unit={pioreactorUnit}
/>
```

Rules:

- Use `size="small"` for inline entity labels.
- Add `clickable` only when the Chip performs an action or navigation.
- Do not make a decorative Chip focusable.
- Keep labels selectable in copy-heavy tables such as logs.
- Use the singular `PioreactorIcon` for one unit and `PioreactorsIcon` for an
  aggregate target.
- Do not use a Chip for arbitrary prose.
- Tags use small `variant="outlined"` Chips and do not need entity icons.

Exceptions:

- **Selects and dropdown options:** use plain text. An aggregate option may use
  `PioreactorsIcon` plus text, but not a Chip.
- **Page, card, and dialog titles:** use Typography. A raw icon may precede the
  title when it adds context, but do not put the title in a Chip.
- **Breadcrumbs:** use linked text so the hierarchy stays visually quiet.
- **Buttons:** use `startIcon` or `endIcon`; do not put a Chip inside a button.

### Status Chips

Use a status Chip for compact state such as Active, Ready, or Lost.

- Pair color with visible text and, where available, a state icon.
- Status Chips are not clickable unless changing the state is their explicit
  action.
- A transparent background is acceptable for a low-emphasis positive status,
  such as the current Active treatment.
- Do not use color alone for ready/lost/error distinctions.

## Tables and data lists

Choose the row treatment based on interaction, not on the page.

### Non-clickable tables

Tables whose rows are primarily scanned, selected as text, or contain separate
links/actions must be zebra striped.

Examples:

- Experiments table
- Paginated event and system log tables
- Passive inventory or summary tables

```jsx
const ZebraTableRow = styled(TableRow)(() => ({
  "&:nth-of-type(odd)": {
    backgroundColor: "#F7F7F7",
  },
  "&:nth-of-type(even)": {
    backgroundColor: "#FFFFFF",
  },
}));
```

Rules:

- Odd rows are `#F7F7F7`.
- Even rows are `#FFFFFF`.
- The table head is `#FFFFFF`; it is not part of the zebra sequence.
- Links and action buttons inside the row remain independently interactive.
- A row with a link in one cell is still a non-clickable row unless clicking
  the row background also navigates.

### Clickable-row tables

Do not zebra stripe a table when clicking anywhere on a row opens that row.
Use a white base with an explicit hover and keyboard-focus treatment.

Examples:

- Calibrations table
- Estimators table

```jsx
<TableRow
  hover
  tabIndex={0}
  sx={{
    cursor: "pointer",
    backgroundColor: "#FFFFFF",
    "&:hover": { backgroundColor: "#F7F7F7" },
    "&:focus-visible": {
      outline: "2px solid",
      outlineColor: "primary.main",
      outlineOffset: "-2px",
    },
  }}
  onClick={openRow}
  onKeyDown={(event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openRow();
    }
  }}
>
```

Rules:

- A clickable row must have `cursor: pointer`.
- Hover uses `#F7F7F7`.
- Keyboard focus must be visible.
- Enter and Space must activate the same navigation as click.
- Prefer a real link in the primary identifying cell even when the full row is
  clickable, so browser link behavior remains available.
- Nested controls must stop row navigation and remain keyboard accessible.
- Do not rely on hover alone; touch and keyboard users must receive equivalent
  behavior.

### Table structure

- Use semantic MUI table components: `TableContainer`, `Table`, `TableHead`,
  `TableBody`, `TableRow`, and `TableCell`.
- Use `size="small"` for operational data tables.
- Use a `TableContainer` with horizontal overflow so narrow viewports do not
  break the page.
- Use `stickyHeader` for tables that scroll vertically within a bounded area.
- Keep header labels short and use `UnderlineSpan` or a tooltip only when a
  term needs explanation.
- Align prose and identifiers left. Align numeric values right. Keep one
  alignment convention per column.
- Compact data rows normally use about `6px` vertical cell padding. Rows with
  descriptions may use about `10px`.
- Empty, loading, and error states occupy the table region; they must not cause
  the surrounding controls to jump unpredictably.

### Log severity

Severity fill overrides zebra fill:

1. Error: `#FF8F7B`
2. Warning: `#FFEFA4`
3. Notice: `#ADDCAF`
4. Other levels: inherit the zebra row background

Default log cells must use `backgroundColor: "inherit"` or no cell background.
Setting every normal cell to white hides the zebra pattern.

## Cards and sections

- Use a `Card` to group one conceptual region, such as a chart, editor,
  Pioreactor summary, or form.
- Cards use the default white MUI surface and default shape unless the feature
  has a specific visual reason to differ.
- The page header remains outside Cards.
- A Card title uses `h2` semantics, normally with `variant="h6"`.
- Use `CardActions` for actions that belong to the entire Card.
- Avoid stacking Cards solely to create padding. Use `Box`, `Stack`, or `Grid`
  for layout.
- Avoid custom shadows and corner radii for ordinary Cards.

## Buttons and actions

### Hierarchy

- **Contained primary:** the main commit action, such as Save, Start, Export,
  Upload, or Update.
- **Text primary:** navigation, secondary actions, and toolbar actions.
- **Secondary red:** destructive or interrupting actions, such as Delete,
  Remove, Stop, Clear, or Unassign.
- **IconButton:** compact universal actions only. It must have an `aria-label`
  and usually a tooltip.

Rules:

- Use sentence case.
- Use an icon plus a text label for unfamiliar or consequential actions.
- Disable an async action immediately after activation and show progress in or
  beside the control.
- If a disabled action's reason is not obvious, explain the unmet condition.
- Confirm destructive actions using the shared confirmation flow.
- Do not use color as the only indication that an action is destructive.

## Forms and filters

- Use `FormLabel` or a `TextField` label. Do not depend on placeholder text as
  the only label.
- Mark required fields before submission.
- Use small controls for filter toolbars and normal controls for primary forms.
- Page-level filters should update the affected region without moving the page
  title or action group.
- Meaningful filters, sorting, and pagination should be represented in the URL
  when users may need to bookmark, refresh, or share the view.
- Do not use Chips as `Select` values or `MenuItem` contents.
- Preserve user input after validation or server errors.

## Dialogs

- Every dialog must have a visible close `IconButton` in the top-right corner.
  The icon must be MUI's `CloseIcon`.
- Standard MUI Escape and backdrop dismissal should remain enabled.
- A destructive confirmation may restrict backdrop dismissal, but must still
  present explicit Cancel and Confirm actions.
- The dialog title is Typography, not a Chip.
- Optional Pioreactor context may appear as a small icon and secondary text
  above the dialog title.
- Dialog actions place Cancel before the primary action.
- Calls to the shared confirmation flow that set `confirmationButtonProps`
  must include `{ color: "primary", sx: { textTransform: "none" }, variant: "contained" }`.
- Calls to the shared confirmation flow that set `cancellationButtonProps`
  must include `{ color: "secondary", sx: { textTransform: "none" } }`.
- Long-running work must show immediate progress and prevent duplicate
  submission.

## Feedback and state

- Report server errors that affect the current region with:

  ```jsx
  <Alert severity="error">{msg}</Alert>
  ```

- Use field `error` and `helperText` for validation errors that belong to one
  input.
- Use `frontend/src/components/RequirementsAlert.jsx` when the user must
  complete setup before using a feature, such as creating a calibration or
  completing a self-test.
- Error copy should say what failed and what the user can do next.
- Use the shared Snackbar wrapper for transient success or local action
  feedback. Snackbars must use the bottom-center position.
- A Pioreactor card may flash a subtle, brief primary-color halo around a pill
  when a live update changes the pill's visible value: state changes flash
  the activity status pill, and displayed setting changes flash that setting's
  value pill. Initial hydration, repeated values, and telemetry without a
  visible activity remain quiet; reduced-motion mode shows the
  updated text without the extra flash.
- Use `CircularProgress` when an operation takes seconds.
- Use a `Backdrop` only when the user truly must not interact with the page
  until the operation completes. Backdrops should be used very rarely.
- Reserve content space for loading states to avoid layout shifts.
- Empty states should explain what is empty and, when useful, provide the next
  action.

## Responsive and accessible behavior

- Page headers and action groups must wrap instead of overflowing.
- Tables must scroll horizontally inside their container, not widen the whole
  page.
- Standalone touch controls should provide at least a 44px hit area.
- Dense table links and Chips may be visually compact, but must have clear
  spacing, visible keyboard focus, and must not be the only tiny target for a
  critical workflow.
- Do not remove focus indicators.
- Anything available on hover must also be available through focus or tap.
- Do not use color as the sole carrier of state.
- Do not make an entire row clickable without keyboard activation and visible
  focus.
- Keep document heading order valid for screen-reader navigation.

## Implementation rules

- Prefer existing MUI components and `sx`.
- Use theme palette values for new work rather than new hex literals.
- When a visual rule repeats across pages, centralize it in the theme or a
  focused shared component.
- A shared component should encode a settled rule, not hide unresolved design
  differences.
- The likely first shared patterns are `PageHeader`, zebra table rows, clickable
  table rows, and entity Chips.
- Do not inspect or edit `core/pioreactor/web/static/`; it is generated output.

## Reference implementations

These are useful current examples, even where surrounding code may still have
unrelated drift:

| Pattern | Reference |
| --- | --- |
| Zebra data table | `frontend/src/Experiments.jsx` |
| Zebra paginated logs | `frontend/src/components/PaginatedLogsTable.jsx` |
| Clickable rows | `frontend/src/Calibrations.jsx`, `frontend/src/Estimators.jsx` |
| Pioreactor entity Chip | `frontend/src/components/PaginatedLogsTable.jsx` |
| Detail metadata Chips | `frontend/src/SingleCalibrationPage.jsx`, `frontend/src/SingleEstimatorPage.jsx` |
| Title and actions header | `frontend/src/Inventory.jsx`, `frontend/src/Pioreactors.jsx` |
| Status colors | `frontend/src/utils/color.js` |
| App palette and canvas | `frontend/src/App.jsx` |

## Known inconsistencies

These are design debt, not alternate approved patterns.

| Area | Intended rule | Current inconsistency |
| --- | --- | --- |
| Page heading semantics | One `h1` per route page | Calibrations, Estimators, Plugins, Protocols, Export data, Leader, Configuration, Logs, System logs, and Experiment Profiles use `component="h2"` for the top-level title in at least one route state. |
| Header divider | Every normal page header ends with a divider | Experiments, Configuration, experiment profile create/edit, Logs, and System logs omit the standard divider. |
| Header location | Page title sits outside content Cards | Start new experiment places its page title inside the form Card. |
| Detail headers | Back navigation is separate from the record `h1` | Single calibration and single estimator pages mark the back button container as the `h1`; the actual record title is an `h2` inside the Card. |
| Stable page titles | Filters are below or adjacent to the title | Logs and System logs place two `Select` controls inside the heading, making the title visually and semantically unstable. |
| Header spacing | One responsive title/action layout | Header margins currently vary between `5px`, `mb: 1`, `mb: 2`, and omitted spacing; action wrapping is inconsistent. |
| Zebra logs | Non-clickable log rows alternate `#F7F7F7` and `#FFFFFF` | `LogTable.jsx` and `LogTableByUnit.jsx` set normal cells to white, unlike `PaginatedLogsTable.jsx`, so embedded recent-log tables are not zebra striped. |
| Clickable row accessibility | Whole-row navigation has focus and keyboard activation | Calibration and estimator rows have `onClick` and pointer hover but are not keyboard-focusable and do not handle Enter or Space. |
| Row color tokens | Zebra and hover colors come from one shared rule | `#F7F7F7` is repeated independently in Experiments, Plugins, logs, Calibrations, and Estimators. |
| Pioreactor labels | Pioreactor references in content use a small icon Chip | `MissingWorkerModelModal.jsx` and some operational lists use raw icon-plus-text labels outside title or Select contexts. |
| Heading construction | Typography owns its weight and semantics | Some pages use nested bold `Box` elements, some use `sx={{ fontWeight: "bold" }}`, and others leave the same heading unbolded. |
| Spacing tokens | Layout uses theme spacing | Several headers, editors, and controls use one-off pixel margins and widths for ordinary layout. |

### Recommended cleanup order

1. Standardize page headers and semantic heading levels.
2. Fix clickable row keyboard behavior.
3. Make all non-clickable log tables use the zebra rule.
4. Move zebra, hover, and repeated status colors into shared theme tokens.
5. Normalize Pioreactor entity labels outside titles, breadcrumbs, and Selects.
