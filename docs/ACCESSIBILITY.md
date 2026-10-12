# Accessibility (target: WCAG 2.2 AA)

**Status: automated checks pass; a full audit is NOT complete.** Automated tools catch only part of WCAG. The manual
screen-reader checks below have not been performed (no NVDA/JAWS/VoiceOver/TalkBack available in this environment) and
must be done before claiming conformance.

## Automated coverage (runs in CI)

| Check | Where | Result (latest run) |
|---|---|---|
| axe-core, rule sets `wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa` | `frontend/e2e/a11y.e2e.ts` — login (incl. error state), register, onboarding, all 22 main pages, task dialog, quick-add with interpretation, **ringing alarm dialog**, calendar month view, 4 pages at 375 px mobile | 0 violations of any impact |
| Skip link is the first tab stop and moves focus to `<main>` | a11y.e2e | pass |
| Dialog focus: initial focus inside, Tab can't escape (40 presses), Escape closes, **focus returns to the opener** | a11y.e2e + `components.test.tsx` | pass |
| Alarm dialog: `alertdialog` with accessible name, initial focus on Snooze, operable by keyboard, Esc = snooze | a11y.e2e + component tests | pass |
| Calendar: labelled Previous/Next/Today buttons, announced title (`aria-live`), view switch as radio group, keyboard-scrollable labelled region | a11y.e2e | pass |
| Target size ≥ 24×24 CSS px (2.5.8) on mobile for links, buttons, inputs (labels count as targets) | a11y.e2e | pass |
| Reflow at 320 CSS px without horizontal scroll (1.4.10) | a11y.e2e | pass |
| 200% text without horizontal scroll at 1280 px (1.4.4) | a11y.e2e | pass |
| Reduced motion: no animation longer than 10 ms when `prefers-reduced-motion: reduce` (2.3.3 best practice) | a11y.e2e | pass |
| Static lint: `eslint-plugin-jsx-a11y` rules via oxlint (`npm run lint`) | src + e2e | 0 errors / warnings |
| Status not by colour alone, labelled toggles (`aria-pressed`), form errors linked with `aria-describedby` + `aria-invalid` + `role=alert` | component tests | pass |

## Defects found and fixed in this pass
1. **Secondary text contrast 4.06:1** (PRD colour `#737970` on cream) → token darkened to `#5f655c` (≥ 4.7:1 on every light surface). 1.4.3.
2. **Calendar tasks unreadable** (white on pale amber, 1.17:1) → dark text on task events. 1.4.3.
3. **Calendar days outside the month at 30% opacity** (1.79:1) → muted colour at full opacity. 1.4.3.
4. **Unnamed `role=img` arrow icons** in the calendar toolbar → replaced by DayWell's own labelled toolbar. 1.1.1 / 4.1.2.
5. **Calendar scroll area not keyboard-reachable** → scrolling moved to a focusable, labelled region outside the ARIA grid (a focusable scroller inside the grid broke `grid > rowgroup > row`). 2.1.1.
6. **Focus lost to `<body>` when any dialog closed** (Radix returns focus only to a `<Trigger>`; DayWell opens dialogs programmatically) → `useReturnFocus` restores focus to the opener. 2.4.3.
7. **Small touch targets**: header links (20 px tall), volume slider (16 px), "Take a rest day" (16 px), notification checkboxes → ≥ 24 px. 2.5.8.

## Manual checks still required (not performed)
| Check | How | Why automation can't |
|---|---|---|
| NVDA + Firefox/Chrome (Windows), VoiceOver + Safari (macOS/iOS), TalkBack + Chrome (Android): register → onboarding → quick add → task complete → habit check-off → alarm ring → snooze | Listen for meaningful names, order, state changes; toasts announced once | Announcement quality and verbosity |
| Alarm while a screen reader is running | Does the alertdialog interrupt and announce title + body? Is the sound distinguishable from speech? | Needs real AT + audio |
| Calendar with a screen reader | FullCalendar's grid markup is third-party; check day/event announcements and drag-and-drop alternatives (Edit → change times is the keyboard alternative) | Grid semantics vary by AT |
| Voice control (Dragon / Voice Access) | Every control reachable by its visible label | Label-in-name in practice |
| Windows High Contrast / forced colours | Focus rings, toggles, progress rings visible | axe doesn't evaluate forced colours |
| 400% zoom on desktop, landscape phone | Content and dialogs remain usable | Viewport combinations |
| Cognitive review of copy (tone, error messages) | Plain language, no shaming | Judgement |

## Known limitations
- FullCalendar's drag-and-drop has no keyboard equivalent itself; the accessible alternative is opening the event/task and editing its date/time (fully keyboard-operable).
- Charts (habit history grid, insights bars) have text equivalents (labels, tables, `aria-label`s) but haven't been reviewed with a screen reader.
