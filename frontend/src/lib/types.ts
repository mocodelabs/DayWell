/** API contracts — kept in sync with the DRF serializers (see docs/API_SPEC.md). */

export type ModuleKey = "affirmations" | "reading" | "fitness" | "hydration" | "sleep" | "journal" | "goals" | "mindfulness" | "admin";
export type Tone = "warm" | "calm" | "direct" | "energetic" | "minimal";
export type SectionKey =
  | "briefing" | "progress" | "agenda" | "priorities" | "reminders" | "habits" | "affirmation" | "reading" | "fitness" | "hydration" | "evening";

export interface User {
  id: number;
  email: string;
  display_name: string;
  email_verified: boolean;
  date_joined: string;
}

export interface Preferences {
  time_zone: string;
  locale: string;
  date_format: "DMY" | "MDY" | "YMD";
  time_format: "24h" | "12h";
  week_start: number;
  theme: "system" | "light" | "dark";
  reduced_motion: boolean;
  text_scale: string;
  onboarding_completed: boolean;
  onboarding_completed_at: string | null;
  focus_areas: string[];
  modules: Record<ModuleKey, boolean>;
  dashboard_layout: { key: SectionKey; visible: boolean }[];
  greeting_enabled: boolean;
  tone: Tone;
  briefing_style: "short" | "detailed";
  greeting_time: string;
  morning_notification: boolean;
  evening_summary: boolean;
  evening_time: string;
  wake_time: string;
  bedtime: string;
  work_start: string;
  work_end: string;
  work_days: number[];
  planning_buffer_minutes: number;
  hydration_target: number;
  hydration_unit: "ml" | "oz" | "glass";
  glass_size_ml: number;
  reading_yearly_goal: number;
  weekly_workout_goal: number;
  affirmation_categories: string[];
  default_sound: string;
  alarm_volume: number;
  quiet_enabled: boolean;
  quiet_start: string;
  quiet_end: string;
  quiet_days: number[];
  quiet_behavior: "delay" | "silent";
  missed_policy: "show" | "hide";
  ai_suggestions_enabled: boolean;
  journal_ai_consent: boolean;
  updated_at: string;
}

export interface Me {
  user: User;
  preferences: Preferences;
}

export type Priority = "low" | "normal" | "high" | "urgent";
export type TaskStatus = "pending" | "in_progress" | "completed" | "postponed" | "cancelled";

export interface Category {
  id: number;
  name: string;
  color: string;
  icon: string;
  archived: boolean;
}

export interface Subtask {
  id: number;
  title: string;
  position: number;
  done: boolean;
  done_at: string | null;
}

export interface ReminderOffset {
  id?: number;
  offset_minutes: number;
  anchor: "start" | "deadline";
  series?: boolean;
}

export interface Task {
  id: number;
  title: string;
  description: string;
  notes: string;
  priority: Priority;
  important: boolean;
  status: TaskStatus;
  category: number | null;
  tags: string[];
  scheduled_date: string | null;
  scheduled_time: string | null;
  scheduled_at: string | null;
  time_zone: string;
  duration_minutes: number | null;
  deadline: string | null;
  link_url: string;
  completed_at: string | null;
  postponed_count: number;
  series: number | null;
  series_rule: string | null;
  occurrence_date: string | null;
  detached: boolean;
  subtasks: Subtask[];
  reminders: ReminderOffset[];
  is_overdue: boolean;
  quadrant: "do" | "schedule" | "delegate" | "later";
  created_at: string;
  updated_at: string;
}

export interface TaskInput {
  title: string;
  description?: string;
  notes?: string;
  priority?: Priority;
  important?: boolean;
  category?: number | null;
  tags?: string[];
  scheduled_date?: string | null;
  scheduled_time?: string | null;
  duration_minutes?: number | null;
  deadline?: string | null;
  link_url?: string;
  checklist?: string[];
  recurrence?: string;
  reminders?: ReminderOffset[];
}

export interface CalendarEvent {
  id: number;
  title: string;
  description: string;
  location: string;
  meeting_url: string;
  category: number | null;
  all_day: boolean;
  time_zone: string;
  start_date: string;
  start_time: string | null;
  end_date: string;
  end_time: string | null;
  start: string;
  end: string;
  rrule: string;
  series_end: string | null;
  status: "confirmed" | "tentative" | "cancelled";
  attendance: Attendance;
  reminder_offsets: number[];
  conflicts?: Conflict[];
}

export type Attendance = "" | "attended" | "completed" | "missed" | "skipped";

export interface Occurrence {
  event_id: number;
  key: string;
  title: string;
  start: string;
  end: string;
  all_day: boolean;
  time_zone: string;
  description: string;
  location: string;
  meeting_url: string;
  category: number | null;
  color: string | null;
  status: string;
  attendance: Attendance;
  is_recurring: boolean;
  is_exception: boolean;
  rrule: string;
  local_start: string;
  local_end: string;
}

export interface Conflict {
  a: { event_id: number; key: string; title: string; start: string; end: string };
  b: { event_id: number; key: string; title: string; start: string; end: string };
}

export type OccurrenceStatus =
  | "scheduled" | "dispatching" | "sent" | "snoozed" | "dismissed" | "completed" | "acknowledged" | "rescheduled" | "missed" | "skipped" | "failed" | "cancelled";

export interface Delivery {
  id: number;
  channel: "in_app" | "push";
  kind: string;
  attempted_at: string;
  result: "pending" | "accepted" | "delivered" | "failed" | "expired";
  error: string;
  confirmed_at: string | null;
  retry_count: number;
}

export interface AlarmOccurrence {
  id: number;
  reminder: number;
  reminder_title: string;
  title: string;
  body: string;
  category: string;
  status: OccurrenceStatus;
  status_label: string;
  skip_reason: string;
  last_error: string;
  silent: boolean;
  scheduled_for: string;
  fire_at: string;
  sent_at: string | null;
  delivered_at: string | null;
  audio_status: string;
  audio_played_at: string | null;
  acted_at: string | null;
  dismissed_at: string | null;
  completed_at: string | null;
  snoozed_until: string | null;
  read_at: string | null;
  escalations: number;
  snooze_count: number;
  parent: number | null;
  target_key: string;
  task: number | null;
  sound: string;
  snooze_minutes: number;
  linked: { type: "task" | "event" | "habit"; id: number; key?: string } | null;
  can_complete: boolean;
  deliveries: Delivery[];
}

export interface Reminder {
  id: number;
  title: string;
  message: string;
  category: string;
  kind: "absolute" | "relative";
  priority: "normal" | "high" | "critical";
  dtstart_date: string | null;
  dtstart_time: string | null;
  rrule: string;
  time_zone: string;
  offset_minutes: number;
  anchor: "start" | "deadline";
  task: number | null;
  task_series: number | null;
  event: number | null;
  habit: number | null;
  sound: string;
  vibrate: boolean;
  snooze_minutes: number | null;
  bypass_quiet_hours: boolean;
  repeat_until_ack: boolean;
  repeat_every_minutes: number;
  enabled: boolean;
  next_fire_at: string | null;
  linked: { type: string; id: number } | null;
  upcoming?: string[];
}

export interface NotificationPreference {
  id: number;
  category: string;
  label: string;
  enabled: boolean;
  channels: ("in_app" | "push")[];
  sound: string;
  vibrate: boolean;
  snooze_minutes: number;
  bypass_quiet_hours: boolean;
  min_gap_minutes: number;
}

export interface Diagnostics {
  server_time: string;
  time_zone: string;
  local_time: string;
  push_configured: boolean;
  subscriptions: { active: number; inactive: number };
  scheduler: { heartbeat_at: string | null; healthy: boolean; lag_seconds: number };
  quiet_hours_active: boolean;
  last_push: { attempted_at: string; result: string; http_status: number | null; error: string; confirmed_at: string | null } | null;
  pending_reminders: number;
}

export type TargetType = "binary" | "count" | "duration" | "numeric";

export interface Habit {
  id: number;
  name: string;
  description: string;
  category: string;
  icon: string;
  color: string;
  target_type: TargetType;
  target_value: string;
  unit: string;
  schedule_rule: string;
  times_per_week: number | null;
  start_date: string;
  time_zone: string;
  reminder_time: string | null;
  status: "active" | "paused" | "archived";
  paused_at: string | null;
  streaks_enabled: boolean;
  position: number;
}

export interface HabitCompletion {
  id: number;
  habit: number;
  date: string;
  status: "done" | "partial" | "skipped";
  value: string;
  notes: string;
  completed_at: string | null;
}

export interface HabitProgress {
  scheduled: number;
  done: number;
  partial: number;
  skipped: number;
  rate: number | null;
  total_value: string;
  weekly_target: number | null;
  weeks_met: number | null;
  weeks: number | null;
}

export interface HabitState {
  habit: Habit;
  date: string;
  scheduled: boolean;
  completion: HabitCompletion | null;
  week: HabitProgress;
  streak?: { current: number; best: number; unit: "days" | "weeks" };
}

export interface AgendaItem {
  type: "event" | "task";
  id: number;
  key?: string;
  title: string;
  start: string;
  end: string;
  all_day: boolean;
  location?: string;
  meeting_url?: string;
  attendance?: Attendance;
  color?: string | null;
  is_recurring?: boolean;
  status?: TaskStatus;
}

export interface TaskCard {
  id: number;
  title: string;
  priority: Priority;
  status: TaskStatus;
  scheduled_date: string | null;
  scheduled_time: string | null;
  scheduled_at: string | null;
  deadline: string | null;
  duration_minutes: number | null;
  category: number | null;
  is_overdue: boolean;
  is_recurring: boolean;
}

export interface DashboardHabit {
  id: number;
  name: string;
  icon: string;
  color: string;
  target_type: TargetType;
  target_value: string;
  unit: string;
  value: string;
  status: HabitCompletion["status"] | null;
  times_per_week: number | null;
}

export interface Dashboard {
  generated_at: string;
  local: { date: string; time: string; iso: string; time_zone: string; weekday: string };
  greeting: { headline: string; message: string; part_of_day: string } | null;
  briefing: { style: "short" | "detailed"; schedule: string; getting_started: string; conflicts: string; overdue: string };
  agenda: AgendaItem[];
  next_up: AgendaItem | null;
  tasks_today: TaskCard[];
  priorities: TaskCard[];
  overdue: { count: number; items: TaskCard[] };
  habits: { items: DashboardHabit[]; done: number; total: number };
  reminders: { upcoming: { id: number; title: string; fire_at: string; category: string }[]; active: number; missed: number };
  progress: { tasks_done: number; tasks_total: number; habits_done: number; habits_total: number; events_total: number; events_attended: number; overall: number | null };
  conflicts: Conflict[];
  modules: Record<ModuleKey, boolean>;
  layout: { key: SectionKey; visible: boolean }[];
  evening: { message: string; remaining: { id: number; title: string }[]; headline: string } | null;
  affirmation?: { id: number; text: string; category: string; acknowledged: boolean } | null;
  reading?: {
    current_book: { id: number; title: string; author: string; current_page: number; total_pages: number | null; daily_goal_minutes: number | null } | null;
    minutes_today: number;
    streak: { current: number; read_today: boolean };
    running_session: { id: number; book_id: number; started_at: string } | null;
  };
  fitness?: { plan: { routine_id: number; name: string; time: string | null; duration_minutes: number; location: string; logged_status: string | null }[] };
  hydration?: HydrationDay;
}

export interface HydrationDay {
  date: string;
  total_ml: number;
  target_ml: number;
  unit: "ml" | "oz" | "glass";
  total: number;
  target: number;
  progress: number | null;
  glass_ml: number;
}

export interface Affirmation {
  id: number;
  text: string;
  category: string;
  custom: boolean;
  favorite: boolean;
  active: boolean;
}

export interface DailyAffirmation {
  id: number;
  date: string;
  affirmation: Affirmation;
  viewed_at: string | null;
  acknowledged_at: string | null;
  favorite: boolean;
}

export interface Book {
  id: number;
  title: string;
  author: string;
  cover_url: string;
  category: string;
  status: "want" | "reading" | "completed" | "paused";
  total_pages: number | null;
  current_page: number;
  start_date: string | null;
  target_date: string | null;
  completed_date: string | null;
  daily_goal_minutes: number | null;
  rating: number | null;
  notes: string;
  review: string;
  progress: number | null;
  minutes_total: number | null;
}

export interface BookNote {
  id: number;
  kind: "note" | "highlight" | "quote";
  text: string;
  page: number | null;
  created_at: string;
}

export interface ReadingSession {
  id: number;
  book: number;
  book_title: string;
  date: string;
  started_at: string;
  ended_at: string | null;
  duration_minutes: number;
  start_page: number | null;
  end_page: number | null;
  pages_read: number | null;
  source: "timer" | "manual";
  notes: string;
}

export interface ReadingStats {
  books_completed: number;
  books_completed_this_year: number;
  active_books: number;
  week: { minutes: number; pages: number; sessions: number };
  month: { minutes: number; pages: number; sessions: number };
  streak: { current: number; read_today: boolean };
  yearly_goal: { target: number | null; completed: number; rate: number | null };
  definitions: Record<string, string>;
}

export interface Routine {
  id: number;
  name: string;
  workout_type: string;
  days: number[];
  time: string | null;
  duration_minutes: number;
  location: string;
  prep_buffer_minutes: number;
  reminder_enabled: boolean;
  notes: string;
  active: boolean;
}

export interface WorkoutSession {
  id: number;
  routine: number | null;
  routine_name: string | null;
  date: string;
  started_at: string | null;
  ended_at: string | null;
  workout_type: string;
  planned_minutes: number | null;
  duration_minutes: number;
  status: "completed" | "partial" | "skipped";
  distance: string | null;
  distance_unit: string;
  exercises: { name: string; sets?: number | null; reps?: number | null; weight?: number | null; notes?: string }[];
  effort: number | null;
  notes: string;
}

export interface FitnessSummary {
  sessions: number;
  minutes: number;
  skipped: number;
  planned: number;
  planned_completed: number;
  rate: number | null;
}

export interface FitnessStats {
  week: FitnessSummary;
  month: FitnessSummary;
  total_minutes: number;
  weekly_goal: number | null;
  trend: { week_start: string; sessions: number; minutes: number }[];
  definitions: Record<string, string>;
}

export interface ModuleReminder {
  enabled: boolean;
  time: string | null;
  days: number[];
  every_minutes?: number;
  until?: string;
}

export interface SleepLog {
  id: number;
  date: string;
  bedtime_at: string;
  wake_at: string;
  duration_minutes: number;
  quality: number | null;
  notes: string;
}

export interface JournalEntry {
  id: number;
  date: string;
  title: string;
  body: string;
  gratitude: string[];
  mood: number | null;
  prompt: string;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface MindfulnessSession {
  id: number;
  date: string;
  kind: "breathing" | "meditation" | "reflection" | "stretch";
  planned_seconds: number;
  completed_seconds: number;
  notes: string;
  created_at: string;
}

export interface RangeStats {
  start: string;
  end: string;
  time_zone: string;
  days: {
    date: string; tasks_planned: number; tasks_completed: number; tasks_cancelled: number; tasks_postponed: number; completed_any_day: number;
    habits_scheduled: number; habits_done: number; reading_minutes: number; workouts: number; workout_minutes: number; events: number; events_attended: number;
  }[];
  tasks: { planned: number; completed: number; cancelled: number; postponed: number; completed_any_day: number; open_now: number; rescheduled: number; completion_rate: number | null };
  habits: { items: ({ id: number; name: string; icon: string } & HabitProgress)[]; consistency: number | null; done: number; scheduled: number };
  events: { total: number; attended: number };
  reading: { minutes: number; pages: number; sessions: number; books_completed: number };
  fitness: { sessions: number; minutes: number };
  most_productive_days: { date: string; completed: number }[];
  has_activity: boolean;
  definitions: Record<string, string>;
}

export interface WeeklyInsights extends RangeStats {
  week_start: string;
  outstanding: { id: number; title: string; scheduled_date: string | null; priority: Priority }[];
  accomplishments: string[];
  suggestions: string[];
  review: WeeklyReview | null;
  reflection_questions: string[];
}

export interface WeeklyReview {
  id: number;
  week_start: string;
  went_well: string;
  challenges: string;
  next_focus: string;
  wins: string;
  adjustments: string;
  stats_snapshot: Record<string, unknown>;
  completed_at: string | null;
}

export interface Goal {
  id: number;
  title: string;
  description: string;
  metric: string;
  habit: number | null;
  target_value: string;
  unit: string;
  current_value: string;
  start_date: string;
  due_date: string | null;
  status: "active" | "completed" | "archived";
  completed_at: string | null;
  progress: { value: string; target: string; progress: number | null; expected_progress: number | null; reached: boolean };
}

export interface PlanSuggestion {
  date: string;
  window: { start: string; end: string };
  fixed: { start: string; end: string; title: string }[];
  suggestions: { task_id: number; title: string; start: string; end: string; start_time: string; duration_minutes: number; reason: string }[];
  unplaced: { task_id: number; title: string; duration_minutes: number; reason: string }[];
  free_minutes: number;
  needed_minutes: number;
  overloaded: boolean;
  note: string;
}
