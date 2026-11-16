# ClipForge UI layout spec (owner request 2026-10-31)

Owner wants the app to feel like the reference clipping tool he uses: same page structure, same workflow,
same editing interactions. Reference screenshots (owner-provided, local only, never committed, never
shipped): `.agent/reference/ui/ref-1..5.png`. Look at them for layout and spacing.

Hard limits (SPEC 1, PRD 8): ClipForge name, text logo, ember palette (`#ff6b35`; light theme by default on
`#F5F5F7`, grey dark theme as an option, TASK-200), Phosphor icons, Poppins UI font (OFL, bundled), our own wording. Do NOT copy the reference's logo, brand name, marketing text, images,
illustrations, fonts or icon artwork. Match structure and behavior, not branding.
Nothing in the reference that needs a cloud account (credits, trials, invite members, team, social
login) is built in v1; leave those areas out instead of faking them.

## Design tokens (TASK-196)
All tokens live in `frontend/src/index.css` (Tailwind v4 `@theme`); the only hex
is `--ember: #ff6b35`, everything else references it or the zinc vars.
- Colors: `primary` (ember), `success`, `warning`, `highlight`, `destructive`,
  `overlay` (scrim on thumbnails), plus the shadcn `muted`/`card`/`border` set.
  No raw palette classes (emerald/amber/red/...) in components.
- Type scale: `text-display` (home tagline), `text-title` (page title),
  `text-section` (section heading), `text-body`, `text-caption`.
- Spacing: 4/8 px Tailwind scale; `px-page` (2rem) page gutter, `section`
  (2.5rem) between page sections. Containers: `max-w-form` (64rem) for form
  pages, `max-w-wide` (100rem) for grids; use `pageColumn(width)` from
  `lib/surfaces.ts`.
- Radius: shadcn `--radius` scale. Shadows: `shadow-card`, `shadow-card-hover`,
  `shadow-popover`. Transitions: 180 ms default, disabled under
  prefers-reduced-motion.
- `cn` (`lib/utils.ts`) is extended with these tokens; add any new token class
  group there or tailwind-merge drops it.
- Primitives (`components/ui`): `Button` (default = ember, secondary, ghost,
  outline), `Pill` (tones neutral/primary/success/warning/danger/overlay,
  shapes pill/tag) for status pills and thumbnail tags, `Skeleton` for list
  loading, `EmptyState` (icon, title, one action), `NativeSelect`, `Card`.
  `MEDIA_FRAME` is the thumbnail frame with hover ring.
- `text-micro` (11 px) is for tiny meta labels (rail captions, timestamps).
- `Panel` (`ui/panel.tsx`, TASK-196b): side panel with a section-sized title and
  optional actions; `PanelGroup` is a titled group inside it, `collapsible`
  turns its header into an `aria-expanded` toggle (body stays mounted,
  hidden). The editor rail renders every panel in a `Panel`.
- `NativeSelect block` fills its column; every form select uses `NativeSelect`
  (no raw `<select>`). Card surfaces use `cardClass()`, selectable list rows
  (campaigns, brand templates, chapters) use `choiceClass(selected)`.
- Dialogs/popovers use `shadow-popover`; empty lists use `EmptyState` with one
  action (passive lists like recent alerts have none).
- Intentional exceptions: campaign rule fieldsets stay `rounded-xl border`
  inner groups inside the campaign card; the player toolbar is a toolbar, not
  a card; video-mimicking sizes (`text-[10px]`, `text-[15px]`, BrandPreview)
  stay arbitrary.
- Every interactive element has a visible `focus-visible:ring`.

## Global shell (ref-2, ref-3)
- Full-height dark app, no top marketing nav.
- Left sidebar ~240 px, collapsible to icons (collapse button top-right of sidebar). Text logo top-left.
- Sidebar groups with small muted group labels:
  - "Create": Home, Projects, Brand templates, Media library (v1: Media library only if built, else omit).
  - "Publish" group is v2 (calendar, analytics, social accounts): omit in v1.
  - Bottom: Settings, Help (link to README).
- Top bar on inner pages: breadcrumb (`Projects / <project title>`), centered search field
  ("Search keywords or moments…", cmd+K focuses it), right side: notifications bell (job events).

## Home (ref-2)
- Centered wide rounded pill input with link icon: "Paste a video link" + primary button inside the
  pill on the right ("Get clips"). Under it: "Upload" and (v2) "Google Drive" text buttons.
- Row of rounded tool chips under the input (v1 only the ones that work: "Long video to shorts",
  "Captions only", which also covers reframing; the pressed chip is the clipping mode that the settings
  panel opens with); v2 adds more. Under the input: Upload, Google Drive and Subtitles (an SRT or VTT
  uploaded right away that the next project uses as its transcript).
- "Recent projects" heading + "View all" link; cards: 16:9 thumbnail with status overlay text,
  title (1 line, ellipsis), "<n> clips · <date>", kebab menu (rename, delete).
- Drag-and-drop anywhere on the page uploads a file (full-page drop overlay).

## Settings panel (after link/file accepted)
- Opens as a large centered card below the input (same page), video thumbnail + title + duration
  left with the copyright notice under it (sticky), all SPEC 8.2 controls right, "Save as
  default" bottom-left, primary "Get clips" bottom-right.
- Right column top to bottom: "AI clipping" / "Captions only" tabs (AI: genre, number of clips,
  clip length chips (multi-select, Auto alone), "Find moments about…"); speech language select
  with "Upload SRT or VTT (optional)"; timeframe slider with start/end time inputs; toggles (auto
  headline, auto zoom, auto cut, auto color, remove fillers); "Presets" / "My presets" tabs
  (caption grid with "No captions", aspect ratio and brand selects / save, apply, delete named
  presets); source rights + credit line.

## Project / clips gallery (ref-3)
- Toolbar: grid/list toggle, tab "Clips (<n>)", right: Select (multi-select mode), Filter, Sort,
  Export all, kebab.
- Grid of 9:16 cards, 6 per row at 1440 px wide (responsive down to 3 at 1280), gap ~16 px.
- Card: 9:16 preview (autoplay muted on hover), small "Edited" tag top-right when edited,
  duration chip bottom-right ("00:00 01:40" style current/total), reframe-mode chip bottom-left.
- Under the card: large bold score number (green >=80, yellow 60-79, gray <60) left, then icon
  buttons: schedule (v2, omit in v1), download, edit (scissors). Title below, 2 lines, ellipsis.
- Click score -> popover with Hook/Flow/Value/Trend bars + reason text.
- Select mode: checkbox on each card, bulk download/delete bar at bottom.

## Clip editor (ref-4) — the most important screen
Full-screen, no app sidebar.
- Top bar: back arrow, clip title (editable inline, ellipsis), right: autosave status text
  ("All changes saved" / "Unsaved changes" / "Saving…" / "Autosave off") with a cloud on/off
  toggle, undo, redo, "Version history" (clock icon: dialog listing saved versions newest first,
  "Current" pill, "Restore" per version), "Save changes" (disabled until dirty), primary "Export"
  (render + download), avatar area omitted.
- Left column (~45% width): transcript editor.
  - Top tool row: "Speech cleanup" button (opens filler/pause removal review), search in transcript,
    filter, download transcript.
  - "Extend a clip" button above the text: shows grayed context before/after with "extend to here".
  - Running text, word-level spans. Pauses shown inline as small gray pills with their length
    ("0.96s"); removed parts shown as a highlighted strike/marker block.
  - Select words by drag; floating toolbar appears at the selection: "Add caption" (hook/text),
    "Delete" (adds cut range). Deleted words: struck through, click to restore.
  - Click a word: seek player there. Current word highlighted while playing.
- Center/right: preview.
  - Small toolbar above the player: aspect ratio (9:16 / 1:1 / 16:9), "Layout: Fill|Fit|Split",
    background (for fit), crop tool toggle, tracker on/off.
  - 9:16 player with captions burned in preview (proxy render) and a selectable crop frame with
    corner handles when the crop tool is active (drag to move/resize the crop window). In a fixed
    or tracked scene the drag sets a keyframe of that scene at the playhead (linear between
    keyframes).
  - Subject picker (a track scene before its first track, or after "Pick another subject"): the
    source frame at the playhead; click the subject or drag a box around it; "Tracking the
    subject…" over the frame while the backend tracks it, then the saved preview shows the result.
  - Layout drawer reframe section: "Custom ratio" (W:H from 1:4 to 4:1, set on the clip; the toolbar
    aspect menu lists 9:16, 1:1, 4:5, 16:9 and the clip's custom ratio), the project's reframe style
    (chosen in the settings panel: Automatic, Podcast, Stand-up, Gaming, Vlog) and a track hint.
  - Layout drawer: how the scene at the playhead is framed (Auto / Track / Fixed / Fit / Split,
    titled "Scene i of n · start – end" when the clip has more than one scene), "Pick the subject"
    / "Pick another subject" for a track scene, and "Apply to all scenes".
- Far-right vertical icon rail (~72 px, scrolls when short) with labeled icons opening a right drawer:
  Captions, Layout, Sections, Transitions, Brand, Text (hook), Text layers, Media, Score, Rules.
  - Media drawer: upload, kind filter (All / Video / Images / Audio), thumbnail grid; drag a tile onto
    a track that can play it (the track highlights) or press + to add it at the playhead.
  - Text layers drawer: "n of 5 text layers", "Add text" at the playhead, list, and for the selected
    layer: text, font, size, colors, outline, background box, position, in/out animation + length.
  - Transitions drawer: one transition for all jump cuts, one per section cut ("Section i to i+1",
    "Use the first for all"), each with a length slider.
- Bottom timeline (full width, ~200 px tall, "Hide timeline" toggle):
  - Control row: hide timeline, split at playhead, delete selection, snap toggle, skip back, play/pause,
    skip forward, "current / total" time, zoom slider with -/+.
  - Time ruler with seconds labels; playhead line with handle draggable across all rows.
  - Layout/segment row: small labeled blocks per segment, split at scene cuts and user splits,
    labeled with how the scene is framed ("Auto", "Track", "Fixed", "Fit", "Split"); clicking one
    selects it and moves the playhead into it.
  - Keyframes row (while the playhead is in a fixed or tracked scene): a diamond per crop
    keyframe; click seeks there, drag moves it (inside the scene), Delete removes it.
  - Video row: filmstrip of thumbnails across the source range; the clip is a bright bordered box
    with drag handles at both ends (trim/extend); outside the clip is dimmed. Cut ranges show as gaps.
  - Audio row: waveform under the filmstrip.
  - Effects row above (speed markers etc.) is v2.
- Keyboard: space play/pause, Delete cut selection (or remove the selected layer item), cmd+Z /
  shift+cmd+Z, S split, left/right 1 frame, shift+left/right 1 s, +/- zoom, < / > playback speed,
  cmd+C / cmd+V copy a selected layer item and paste it at the playhead. The control row has a
  playback speed menu (0.25×–2×) after the time.

## Modals (ref-5 style)
- Centered dark modal ~560 px, title top-left, close X top-right, content as 2-column grid of
  bordered tiles, secondary button bottom-right. Use this pattern for template pickers and (v2)
  social account connect.
