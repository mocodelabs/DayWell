# DayWell — Product Requirements Document (PRD)

> Source of truth for the build. Version 1.0 — proposed for development. Supplied by the product owner; reproduced here
> verbatim in substance. Implementation status against each section lives in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

- **Product:** DayWell — Personal Operations & Wellness Companion
- **Product type:** Responsive web application and installable Progressive Web App (PWA), designed for mobile-first use
- **Primary audience:** Individuals who want to organise daily responsibilities, build healthy routines and improve personal productivity
- **Initial deployment:** Cloud-hosted application with support for installation on mobile and desktop devices

## 1. Product overview

### 1.1 Vision
DayWell is a personal daily operating system that combines scheduling, task management, calendar management, alarms, wellness routines, habit tracking and supportive conversational interactions. Unlike a conventional productivity application, DayWell should feel like a thoughtful personal companion. It helps users prepare for the day, remember commitments, build sustainable habits and reflect on their progress.

### 1.2 Problem statement
People commonly manage their lives through disconnected applications: calendars for appointments, alarms for wake-up times, task managers for work, notes for personal goals and separate applications for exercise or reading. This fragmentation leads to:
- Missed appointments and forgotten tasks.
- Inconsistent gym, reading and personal development routines.
- Poor visibility into how time is spent.
- Excessive or poorly timed notifications.
- Difficulty balancing professional responsibilities and personal well-being.
- Productivity tools that feel impersonal, demanding or overwhelming.

DayWell consolidates these functions into one customisable daily experience.

### 1.3 Product goals
1. Provide one reliable place to organise daily activities.
2. Support recurring and one-time reminders, including configurable alarm behaviour.
3. Generate a personalised daily briefing.
4. Support configurable wellness habits and progress tracking.
5. Help users understand their accomplishments and missed commitments without shaming them.
6. Maintain a fast, accessible, secure and reliable user experience.
7. Work well on desktop, Android and iOS within the capabilities of each platform.

### 1.4 Non-goals for the initial release
Not: a medical diagnosis or treatment application; a replacement for emergency alert services; a full project-management suite for large teams; a social network; a comprehensive fitness coaching platform; a full audiobook, ebook or digital library service; a guarantee of alarm delivery when the operating system or browser prevents background execution.

## 2. Target users
1. **Busy professionals and entrepreneurs** — meetings, tasks, deadlines, personal routines and business responsibilities.
2. **Students and lifelong learners** — study periods, reading targets, assignments, revision and personal development.
3. **Wellness-oriented individuals** — exercise, hydration, meditation, consistent sleep and healthy routines.
4. **People seeking structure** — a clear plan for the day, gentle reminders and positive reinforcement.
5. **Users with highly customisable schedules** — different weekday/weekend routines, variable hours, travel-aware scheduling, flexible reminders.

## 3. Product principles
Warmth · Simplicity (today's next action immediately visible) · Autonomy (features, routines, notification intensity, tone) · Reliability (persistent reminders; distinguish scheduled, delivered and completed) · Flexibility (one-time, recurring, postponed, rescheduled) · Non-judgement (missed tasks trigger helpful options, not guilt) · Privacy (private by default) · Accessibility (screen readers, keyboard, reduced motion, readable contrast) · **Honesty: never claim an alarm played or a notification was delivered unless the system has evidence of that outcome.**

## 4. Information architecture
Navigation: Today, Calendar, Tasks, Habits, Growth, Insights, Settings. Compact bottom navigation on mobile, sidebar on larger screens. Today is the landing page.

### 4.1 Today
Personalised greeting; current date and local time; weather only if explicitly enabled and supported; daily progress; today's agenda and next upcoming event; priority tasks; active reminders; habit checklist; affirmation of the day (if enabled); reading and exercise goals (if enabled); quick-add actions; a warm end-of-day summary when appropriate. Users must be able to hide or reorder optional dashboard sections.

### 4.2 Calendar
Day, week and month views. Create/edit/delete events; start and end time; all-day events; location and meeting links; description and notes; colour categories; recurrence rules; reminder offsets; completion/attendance status; conflict detection; search and filtering; drag-and-drop rescheduling; import/export through calendar formats; optional external calendar sync in a later phase. The calendar must distinguish appointments from flexible tasks and habits.

## 5. Scheduler and task management
### 5.1 Task creation
Title, description, priority (low/normal/high/urgent), scheduled date, optional time, optional deadline, estimated duration, category, tags, checklist/subtasks, recurrence, reminder settings, completion status, notes, optional link or attachment, created/updated timestamps. States: Pending, In progress, Completed, Postponed, Cancelled. Overdue tasks clearly identified without dominating the interface.

### 5.2 Quick-add
Create a task from any primary screen with one prominent action. Support structured quick entry such as *"Call the supplier tomorrow at 10 AM and remind me 15 minutes before."* If natural-language parsing is implemented, show the interpreted date, time and reminder before saving. Do not silently guess ambiguous dates.

### 5.3 Prioritisation
Three recommended daily priorities; full task list; optional Eisenhower categorisation; overdue items; tasks due today; upcoming deadlines. The app may recommend a plan but must not automatically move or delete commitments without permission.

### 5.4 Recurrence
Daily, weekly, monthly, yearly and custom (every weekday at 6:30; Mon/Wed/Fri; monthly on the 5th; every two weeks; selected days; end after a date or number of occurrences). Editing a recurring item must allow choosing one occurrence or the entire series.

## 6. Reminders and alarm engine (core feature)
### 6.1 Types
One-time, recurring, event, task deadline, habit, reading, gym, hydration, bedtime and wake-up, custom.

### 6.2 Configuration
Title and message; date and time; time zone; recurrence; sound; vibration where supported; notification permission status; snooze duration; dismiss; mark complete where applicable; escalation/repeat if enabled; quiet hours; priority; linked task, event or habit. Choose among sounds, adjust volume where permitted, preview sounds, choose vibration.

### 6.3 Alarm behaviour
1. A reminder becomes due at its scheduled time. 2. The system attempts the configured delivery. 3. When the app is open, an in-app alarm may play audio until dismissed or snoozed. 4. Browser notifications only after permission. 5. A service worker may display notifications in the background. 6. Snoozing creates a new scheduled occurrence without losing history. 7. Dismissing records the dismissal time. 8. Completing a linked task is recorded independently of dismissing. 9. Repeated reminders must not multiply after refreshes or reconnects. 10. Missed reminders surfaced on the next visit.

### 6.4 Reliability and platform limitations
A PWA cannot guarantee continuous ringing while the browser is closed, the device asleep or the app suspended. Therefore: browser notifications and in-app audio initially; permission via user-initiated action; server-side scheduling and push; don't assume push can play arbitrary audio or override silent modes; provide an alarm test and setup checklist; communicate limitations; plan native apps if dependable background ringing becomes mandatory; never claim an alarm sounded because its time has passed.

### 6.5 Quiet hours
Start/end, days of the week, categories that may bypass, delay vs. silent delivery. Critical reminders bypass only with explicit opt-in.

### 6.6 Missed reminder recovery
Review missed reminders: mark complete, snooze, reschedule, dismiss, keep overdue. Never auto-complete.

## 7. Warm interaction
### 7.1 Morning greeting
At a configurable time or first daily opening, a greeting for the local time, using preferences and real schedule data — never invented activities or achievements.

### 7.2 Briefing contents
Greeting; date (weather if enabled); number of events; top priorities; first upcoming event; active wellness routines; affirmation (if enabled); conflicts; a supportive suggestion. Short or detailed.

### 7.3 Tone preferences
Warm and friendly; Calm and mindful; Direct and concise; Energetic and motivational; Minimal. Greetings can be disabled.

### 7.4 Context-aware messaging
Start of day, before a meeting, gym reminder, missed habit, end of day — never manipulative, shaming or excessively repetitive.

### 7.5 Deduplication
The same event must not trigger duplicate messages through both the briefing and the reminder engine unless configured. Per-category frequency controls.

## 8. Affirmations and mindfulness (optional)
Categorised library (confidence, focus, gratitude, resilience, self-compassion, consistency, learning, calmness, personal growth); one per day; favourites; history; reminder time; enable/disable; custom affirmations; share/copy; track viewed/acknowledged. Not presented as solutions to mental-health problems. Optional lightweight breathing/reflection/meditation timers — not clinical interventions.

## 9. Reading and learning tracker
Library (manual entry; metadata integration optional): title, author, cover, category, status (want/reading/completed/paused), start date, target date, total pages, current page, reading goal, notes/highlights, rating/review, favourite quotes. Reminders (daily or selected days, duration, snooze, reschedule, optional timer). Sessions (start, end, duration, pages, book, notes; manual logging). Statistics (books completed, active, time this week/month, pages, streak, yearly goal) — streaks must not imply failure after a break.

## 10. Gym and fitness
Schedule (days, time, duration, location, routine, prep/travel buffer, reminders, rest days). Simple log (date, type, planned/actual duration, status, optional exercises/sets, optional distance, notes). Statistics (sessions this week/month, total time, planned vs completed, trends). Support all abilities without judgement.

## 11. Habit tracker
Configurable, not hard-coded: name, description, category, icon, schedule and frequency, binary/numeric/duration/count targets, reminders, completion tracking, notes, optional streaks, weekly and monthly progress. Pausing keeps history.

## 12. Additional optional modules
Hydration (target, quick-add, reminders, progress, units); Sleep and bedtime (planned times, wind-down reminders, evening checklist, manual log, consistency — no clinical claims); Journaling and gratitude (entries, prompts, mood, search; private and excluded from third-party AI without explicit consent); Personal finance reminders (bills, renewals, savings check-ins, manual tracking — no account access); Chores and personal administration (chores, shopping lists, renewals, maintenance, errands, appointments); Weekly planning and review (planning session; summary of tasks, events, habits, reading and gym, outstanding tasks, wins, reflection, suggested adjustments).

## 13. Smart daily planning
Arrange flexible tasks around fixed appointments: identify fixed events; account for durations, working hours, buffers and breaks; identify conflicts; suggest slots; preserve priority and deadlines; highlight overloaded days; accept or reject every change. Never move fixed appointments. AI suggestions optional and clearly distinguished.

## 14. Notification centre
History with category, related item, scheduled time, delivery status where available, read/dismissed/completed status, snooze/reschedule options, channel. Category-level controls.

## 15. Insights and analytics
Daily summary; weekly overview (completion rate, habit consistency, time on logged activities, most productive days, missed and rescheduled commitments, goal progress); monthly and yearly trends. Use actual recorded data and explain the calculations. Never interpret missed tasks as laziness or failure.

## 16. Accounts and onboarding
Email registration, secure login, password reset, email verification where configured, logout, session management, OAuth later. Onboarding: welcome; what help is wanted; modules; wake/bed times; tone; notification preferences; permission in context; optional first routine; first dashboard. Skippable. Profile: display name, time zone, locale, time/date formats, week start, notifications, theme, accessibility, export and deletion.

## 17. Data model
Entities: User, UserPreference, NotificationPreference, Category, Task, TaskSubtask, TaskRecurrence, CalendarEvent, EventRecurrence, Reminder, ReminderOccurrence, NotificationDelivery, Habit, HabitSchedule, HabitCompletion, Affirmation, UserAffirmation, Book, ReadingSession, WorkoutRoutine, WorkoutSession, WaterIntake, JournalEntry, Goal, DailySummary, WeeklyReview, DeviceSubscription, AuditEvent. Store timestamps in UTC; preserve IANA zones; compute recurrence in local rules; store occurrences separately where needed; transactions for state changes; idempotency keys for delivery; indexes on owner/date/status/due fields; appropriate cascade/protect rules; avoid hard deletion where history must be kept.

## 18. Non-functional requirements
- **Performance:** dashboard API p95 < 500 ms under normal load; paginate large collections; efficient queries; loading/empty/success/error states.
- **Security:** authentication and ownership; server-side validation; secure hashing; CSRF; narrow CORS; rate limits; secrets in env; HTTPS; secure push endpoints; no cross-user access; export and deletion; never log passwords, journal content or secrets.
- **Accessibility:** WCAG 2.2 AA; keyboard; labels; screen readers; contrast; reduced motion; scalable text; status not by colour alone.
- **Reliability:** persisted reminders; durable background jobs; bounded retries; recorded attempts; idempotent jobs; monitored scheduling; explicit downtime recovery; never mark unconfirmed notifications delivered.
- **Privacy:** private by default; no public profiles; no sale of data; minimal collection; optional modules; transparent permissions; clear retention/deletion.

## 19. Recommended architecture
React + TypeScript + Vite + Tailwind, accessible components, React Router, TanStack Query, React Hook Form + Zod, a maintained calendar component, PWA manifest + service worker, IndexedDB for limited offline. Python/Django/DRF, PostgreSQL, Redis, Celery + Beat. Web Notifications, service worker + Web Push, in-app audio, optional native integration. Docker, environment config, production PostgreSQL/Redis, migrations, structured logging, tests and CI/CD. A modular monolith — no microservices.

## 20. Acceptance criteria
1. Register, log in, manage profile. 2. Create, edit, complete, postpone, delete tasks. 3. Events at correct local times. 4. Daily and weekly recurrences generate expected occurrences. 5. Reminders persist across restarts. 6. Foreground alarms play a configurable sound when permitted. 7. Browser notifications work after permission. 8. Consistent snooze and dismissal. 9. No duplicate delivery under retries. 10. Personalised greeting and actual agenda. 11. Enable/disable affirmations, reading, fitness. 12. Record and review reading and workouts. 13. Custom habits with progress. 14. Accurate, reproducible weekly summaries. 15. No cross-user access. 16. Usable on mobile and desktop browsers. 17. Graceful empty/permission-denied/network-failure/offline states. 18. Honest alarm-limitation documentation. 19. Critical workflows covered by automated tests. 20. Documented production setup, migrations, backups and deployment.

## 21. Delivery phases
1. Foundation · 2. Daily operations · 3. Warm interaction · 4. Wellness · 5. Insights and polish · 6. Production readiness.

## 22. Success metrics
Onboarding completion; % creating a task or event; weekly actives; reminder completion and dismissal rates; habit-tracking retention; reading/fitness logging frequency; notification opt-out rates; crash/error rates; duplicate reminder incidents; scheduled-job lateness; satisfaction. Do not optimise for clicks or time in app — the goal is a better-organised life outside the app.
