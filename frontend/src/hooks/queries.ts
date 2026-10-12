import { useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { api, type Paginated } from "@/lib/api";
import type {
  AlarmOccurrence, Affirmation, Book, BookNote, CalendarEvent, Category, Conflict, Dashboard, DailyAffirmation, Diagnostics, FitnessStats, Goal,
  Habit, HabitState, HydrationDay, JournalEntry, Me, MindfulnessSession, ModuleReminder, NotificationPreference, Occurrence, PlanSuggestion,
  Preferences, RangeStats, ReadingSession, ReadingStats, Reminder, Routine, SleepLog, Task, TaskInput, WeeklyInsights, WorkoutSession,
} from "@/lib/types";

/** Query keys. Mutations invalidate whole domains so every view stays consistent. */
export const keys = {
  me: ["me"] as const,
  dashboard: ["dashboard"] as const,
  tasks: (params?: object) => ["tasks", params ?? {}] as const,
  task: (id: number) => ["tasks", "detail", id] as const,
  categories: ["categories"] as const,
  occurrences: (start: string, end: string, q?: string) => ["calendar", start, end, q ?? ""] as const,
  event: (id: number) => ["calendar", "event", id] as const,
  alarms: ["alarms"] as const,
  notifications: (params?: object) => ["notifications", params ?? {}] as const,
  reminders: ["reminders"] as const,
  habits: ["habits"] as const,
  insights: ["insights"] as const,
  reading: ["reading"] as const,
  fitness: ["fitness"] as const,
  wellness: ["wellness"] as const,
  affirmations: ["affirmations"] as const,
  goals: ["goals"] as const,
  prefs: ["preferences"] as const,
  notificationPrefs: ["notification-preferences"] as const,
};

function useInvalidate() {
  const qc = useQueryClient();
  return (...domains: QueryKey[]) => Promise.all(domains.map((k) => qc.invalidateQueries({ queryKey: k })));
}

const PLANNING = [keys.dashboard, ["tasks"], ["calendar"], keys.alarms, keys.insights, keys.reminders];

// --- Auth / preferences -------------------------------------------------------------------------------------------------

export const useMe = () => useQuery({ queryKey: keys.me, queryFn: () => api.get<Me>("/auth/me/"), retry: false, staleTime: 60_000 });

export function useUpdatePreferences() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<Preferences> & { complete_onboarding?: boolean }) => api.patch<Preferences>("/preferences/", body),
    onSuccess: (prefs) => {
      qc.setQueryData<Me>(keys.me, (old) => (old ? { ...old, preferences: prefs } : old));
      qc.invalidateQueries({ queryKey: keys.dashboard });
      qc.invalidateQueries({ queryKey: keys.reminders });
    },
  });
}

export const useNotificationPrefs = () =>
  useQuery({ queryKey: keys.notificationPrefs, queryFn: () => api.get<NotificationPreference[]>("/notification-preferences/") });

export function useUpdateNotificationPref() {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: ({ id, ...body }: Partial<NotificationPreference> & { id: number }) => api.patch<NotificationPreference>(`/notification-preferences/${id}/`, body),
    onSuccess: () => inv(keys.notificationPrefs),
  });
}

// --- Dashboard ----------------------------------------------------------------------------------------------------------

export const useDashboard = () =>
  useQuery({ queryKey: keys.dashboard, queryFn: () => api.get<Dashboard>("/dashboard/today/"), refetchInterval: 5 * 60_000 });

export const usePlanner = (date: string, enabled = true) =>
  useQuery({ queryKey: ["planner", date], queryFn: () => api.get<PlanSuggestion>("/planner/suggest/", { date }), enabled });

export function useApplyPlan() {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: (body: { date: string; items: { task_id: number; start_time: string }[] }) => api.post<{ updated: number[] }>("/planner/apply/", body),
    onSuccess: () => inv(...PLANNING, ["planner"]),
  });
}

// --- Tasks --------------------------------------------------------------------------------------------------------------

export const useTasks = (params: Record<string, string | number | boolean | undefined>, enabled = true) =>
  useQuery({ queryKey: keys.tasks(params), queryFn: () => api.get<Paginated<Task>>("/tasks/", params), enabled, placeholderData: (prev) => prev });

export const useTask = (id: number | null) =>
  useQuery({ queryKey: keys.task(id ?? 0), queryFn: () => api.get<Task>(`/tasks/${id}/`), enabled: !!id });

export const useCategories = () => useQuery({ queryKey: keys.categories, queryFn: () => api.get<Category[]>("/categories/"), staleTime: 5 * 60_000 });

export function useCreateCategory() {
  const inv = useInvalidate();
  return useMutation({ mutationFn: (body: Partial<Category>) => api.post<Category>("/categories/", body), onSuccess: () => inv(keys.categories) });
}

export function useCreateTask() {
  const inv = useInvalidate();
  return useMutation({ mutationFn: (body: TaskInput) => api.post<Task>("/tasks/", body), onSuccess: () => inv(...PLANNING) });
}

export function useUpdateTask() {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: ({ id, scope = "this", ...body }: Partial<TaskInput> & { id: number; scope?: "this" | "series" }) =>
      api.patch<Task>(`/tasks/${id}/?scope=${scope}`, body),
    onSuccess: () => inv(...PLANNING),
  });
}

export function useTaskAction() {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: ({ id, action, body }: { id: number; action: "complete" | "reopen" | "start" | "cancel" | "postpone"; body?: object }) =>
      api.post<Task>(`/tasks/${id}/${action}/`, body),
    onSuccess: () => inv(...PLANNING),
  });
}

export function useDeleteTask() {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: ({ id, scope = "this" }: { id: number; scope?: "this" | "series" }) => api.delete(`/tasks/${id}/?scope=${scope}`),
    onSuccess: () => inv(...PLANNING),
  });
}

export function useSubtaskToggle() {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: ({ taskId, id, done }: { taskId: number; id: number; done: boolean }) => api.patch(`/tasks/${taskId}/subtasks/${id}/`, { done }),
    onSuccess: () => inv(["tasks"]),
  });
}

export function useAddSubtask() {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: ({ taskId, title }: { taskId: number; title: string }) => api.post(`/tasks/${taskId}/subtasks/`, { title }),
    onSuccess: () => inv(["tasks"]),
  });
}

// --- Calendar -----------------------------------------------------------------------------------------------------------

export const useOccurrences = (start: string, end: string, q?: string) =>
  useQuery({
    queryKey: keys.occurrences(start, end, q),
    queryFn: () => api.get<{ results: Occurrence[]; conflicts: Conflict[] }>("/calendar/events/occurrences/", { start, end, q }),
    enabled: !!start && !!end,
    placeholderData: (prev) => prev,
  });

export const useEvent = (id: number | null) =>
  useQuery({ queryKey: keys.event(id ?? 0), queryFn: () => api.get<CalendarEvent>(`/calendar/events/${id}/`), enabled: !!id });

export function useSaveEvent() {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: ({ id, ...body }: Partial<CalendarEvent> & { id?: number }) =>
      id ? api.patch<CalendarEvent>(`/calendar/events/${id}/`, body) : api.post<CalendarEvent>("/calendar/events/", body),
    onSuccess: () => inv(...PLANNING),
  });
}

export function useDeleteEvent() {
  const inv = useInvalidate();
  return useMutation({ mutationFn: (id: number) => api.delete(`/calendar/events/${id}/`), onSuccess: () => inv(...PLANNING) });
}

export function useChangeOccurrence() {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: number; key: string } & Record<string, unknown>) => api.post(`/calendar/events/${id}/occurrence/`, body),
    onSuccess: () => inv(...PLANNING),
  });
}

export function useCancelOccurrence() {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: ({ id, key }: { id: number; key: string }) => api.delete(`/calendar/events/${id}/occurrence/?key=${encodeURIComponent(key)}`),
    onSuccess: () => inv(...PLANNING),
  });
}

export function useAttendance() {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: number; key?: string; attendance: string }) => api.post(`/calendar/events/${id}/attendance/`, body),
    onSuccess: () => inv(["calendar"], keys.dashboard, keys.insights),
  });
}

// --- Alarms / notifications / reminders ---------------------------------------------------------------------------------

export const useActiveAlarms = (enabled: boolean) =>
  useQuery({
    queryKey: [...keys.alarms, "active"],
    queryFn: () => api.get<AlarmOccurrence[]>("/alarms/active/"),
    enabled,
    refetchInterval: 20_000,
    refetchIntervalInBackground: false,
  });

export const useMissedAlarms = () => useQuery({ queryKey: [...keys.alarms, "missed"], queryFn: () => api.get<AlarmOccurrence[]>("/alarms/missed/") });

export const useUpcomingAlarms = (hours = 2, enabled = true) =>
  useQuery({ queryKey: [...keys.alarms, "upcoming", hours], queryFn: () => api.get<AlarmOccurrence[]>("/alarms/upcoming/", { hours }), enabled, refetchInterval: 5 * 60_000 });

export function useAlarmAction() {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: ({ id, action, body }: { id: number; action: "snooze" | "dismiss" | "complete" | "keep" | "reschedule" | "shown"; body?: object }) =>
      api.post<AlarmOccurrence | { snoozed_until: string }>(`/alarms/${id}/${action}/`, body),
    onSuccess: (_d, vars) => (vars.action === "shown" ? inv(keys.alarms) : inv(keys.alarms, keys.dashboard, ["notifications"], ["tasks"], keys.habits)),
  });
}

export const useDiagnostics = () => useQuery({ queryKey: [...keys.alarms, "diagnostics"], queryFn: () => api.get<Diagnostics>("/alarms/diagnostics/") });

export function useTestAlarm() {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: (delay_seconds: number) => api.post<{ outcome: string; occurrence: AlarmOccurrence }>("/alarms/test/", { delay_seconds }),
    onSuccess: () => inv(keys.alarms, ["notifications"]),
  });
}

export const useNotifications = (params: Record<string, string | number | undefined>) =>
  useQuery({ queryKey: keys.notifications(params), queryFn: () => api.get<Paginated<AlarmOccurrence>>("/notifications/", params) });

export const useUnreadCount = () =>
  useQuery({ queryKey: ["notifications", "unread"], queryFn: () => api.get<{ count: number }>("/notifications/unread-count/"), refetchInterval: 60_000 });

export function useMarkAllRead() {
  const inv = useInvalidate();
  return useMutation({ mutationFn: () => api.post("/notifications/read-all/"), onSuccess: () => inv(["notifications"]) });
}

export const useReminders = (params: Record<string, string | undefined> = {}) =>
  useQuery({ queryKey: [...keys.reminders, params], queryFn: () => api.get<Paginated<Reminder>>("/reminders/", params) });

export function useSaveReminder() {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: ({ id, ...body }: Partial<Reminder> & { id?: number }) => (id ? api.patch<Reminder>(`/reminders/${id}/`, body) : api.post<Reminder>("/reminders/", body)),
    onSuccess: () => inv(keys.reminders, keys.alarms, keys.dashboard),
  });
}

export function useDeleteReminder() {
  const inv = useInvalidate();
  return useMutation({ mutationFn: (id: number) => api.delete(`/reminders/${id}/`), onSuccess: () => inv(keys.reminders, keys.alarms, keys.dashboard) });
}

// --- Habits -------------------------------------------------------------------------------------------------------------

export const useHabitsToday = (date?: string) =>
  useQuery({ queryKey: [...keys.habits, "today", date ?? ""], queryFn: () => api.get<{ date: string; items: HabitState[] }>("/habits/today/", { date }) });

export const useHabits = (status?: string) =>
  useQuery({ queryKey: [...keys.habits, "list", status ?? ""], queryFn: () => api.get<Paginated<Habit>>("/habits/", { status, page_size: 200 }) });

export const useHabitHistory = (id: number | null, start: string, end: string) =>
  useQuery({
    queryKey: [...keys.habits, "history", id, start, end],
    queryFn: () => api.get<{ scheduled_dates: string[]; completions: HabitState["completion"][]; progress: HabitState["week"] }>(`/habits/${id}/history/`, { start, end }),
    enabled: !!id,
  });

export function useSaveHabit() {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: ({ id, ...body }: Partial<Habit> & { id?: number }) => (id ? api.patch<Habit>(`/habits/${id}/`, body) : api.post<Habit>("/habits/", body)),
    onSuccess: () => inv(keys.habits, keys.dashboard, keys.alarms),
  });
}

export function useHabitAction() {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: ({ id, action, body }: { id: number; action: "complete" | "increment" | "undo" | "pause" | "resume" | "archive"; body?: object }) =>
      api.post<HabitState | Habit>(`/habits/${id}/${action}/`, body),
    onSuccess: () => inv(keys.habits, keys.dashboard, keys.insights),
  });
}

export function useDeleteHabit() {
  const inv = useInvalidate();
  return useMutation({ mutationFn: (id: number) => api.delete(`/habits/${id}/`), onSuccess: () => inv(keys.habits, keys.dashboard) });
}

// --- Insights & goals ---------------------------------------------------------------------------------------------------

export const useWeekly = (weekStart?: string) =>
  useQuery({ queryKey: [...keys.insights, "weekly", weekStart ?? ""], queryFn: () => api.get<WeeklyInsights>("/insights/weekly/", { week_start: weekStart }) });

export const useMonthly = (month?: string) =>
  useQuery({ queryKey: [...keys.insights, "monthly", month ?? ""], queryFn: () => api.get<RangeStats & { month: string; accomplishments: string[] }>("/insights/monthly/", { month }) });

export const useYearly = (year?: number) =>
  useQuery({
    queryKey: [...keys.insights, "yearly", year ?? 0],
    queryFn: () => api.get<{ year: number; months: { month: string; tasks_completed: number; task_completion_rate: number | null; habit_consistency: number | null; reading_minutes: number; books_completed: number; workouts: number }[]; accomplishments: string[] }>("/insights/yearly/", { year }),
  });

export const useDaily = (date?: string) =>
  useQuery({ queryKey: [...keys.insights, "daily", date ?? ""], queryFn: () => api.get<RangeStats & { outstanding: { id: number; title: string }[] }>("/insights/daily/", { date }) });

export function useSaveWeeklyReview() {
  const inv = useInvalidate();
  return useMutation({ mutationFn: (body: Record<string, string>) => api.post("/insights/weekly-reviews/", body), onSuccess: () => inv(keys.insights) });
}

export const useGoals = (status?: string) =>
  useQuery({ queryKey: [...keys.goals, status ?? ""], queryFn: () => api.get<Paginated<Goal>>("/goals/", { status, page_size: 100 }) });

export function useSaveGoal() {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: ({ id, ...body }: Partial<Goal> & { id?: number }) => (id ? api.patch<Goal>(`/goals/${id}/`, body) : api.post<Goal>("/goals/", body)),
    onSuccess: () => inv(keys.goals),
  });
}

export function useGoalAction() {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: ({ id, action, body }: { id: number; action: "check-ins" | "complete" | "archive" | "reactivate"; body?: object }) => api.post<Goal>(`/goals/${id}/${action}/`, body),
    onSuccess: () => inv(keys.goals),
  });
}

// --- Growth modules -----------------------------------------------------------------------------------------------------

export const useTodayAffirmation = (enabled: boolean) =>
  useQuery({ queryKey: [...keys.affirmations, "today"], queryFn: () => api.get<DailyAffirmation>("/affirmations/today/"), enabled });

export const useAffirmationLibrary = (params: Record<string, string | undefined>) =>
  useQuery({ queryKey: [...keys.affirmations, "library", params], queryFn: () => api.get<Paginated<Affirmation>>("/affirmations/library/", { ...params, page_size: 100 }) });

export const useAffirmationHistory = () =>
  useQuery({ queryKey: [...keys.affirmations, "history"], queryFn: () => api.get<Paginated<DailyAffirmation>>("/affirmations/history/") });

export function useAffirmationMutation() {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: (fn: () => Promise<unknown>) => fn(),
    onSuccess: () => inv(keys.affirmations, keys.dashboard),
  });
}

export const useModuleReminder = (path: string) =>
  useQuery({ queryKey: ["module-reminder", path], queryFn: () => api.get<ModuleReminder>(path) });

export function useSaveModuleReminder(path: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ModuleReminder) => api.put<ModuleReminder>(path, body),
    onSuccess: (data) => {
      qc.setQueryData(["module-reminder", path], data);
      qc.invalidateQueries({ queryKey: keys.reminders });
      qc.invalidateQueries({ queryKey: keys.alarms });
    },
  });
}

export const useBooks = (status?: string) =>
  useQuery({ queryKey: [...keys.reading, "books", status ?? ""], queryFn: () => api.get<Paginated<Book>>("/reading/books/", { status, page_size: 100 }) });

export const useBookNotes = (id: number | null) =>
  useQuery({ queryKey: [...keys.reading, "notes", id], queryFn: () => api.get<BookNote[]>(`/reading/books/${id}/notes/`), enabled: !!id });

export const useReadingSessions = () =>
  useQuery({ queryKey: [...keys.reading, "sessions"], queryFn: () => api.get<Paginated<ReadingSession>>("/reading/sessions/", { page_size: 20 }) });

export const useRunningSession = () =>
  useQuery({ queryKey: [...keys.reading, "running"], queryFn: () => api.get<ReadingSession | null>("/reading/sessions/running/") });

export const useReadingStats = () => useQuery({ queryKey: [...keys.reading, "stats"], queryFn: () => api.get<ReadingStats>("/reading/stats/") });

export function useReadingMutation() {
  const inv = useInvalidate();
  return useMutation({ mutationFn: (fn: () => Promise<unknown>) => fn(), onSuccess: () => inv(keys.reading, keys.dashboard, keys.insights) });
}

export const useRoutines = () => useQuery({ queryKey: [...keys.fitness, "routines"], queryFn: () => api.get<Paginated<Routine>>("/fitness/routines/") });
export const useWorkouts = () => useQuery({ queryKey: [...keys.fitness, "sessions"], queryFn: () => api.get<Paginated<WorkoutSession>>("/fitness/sessions/", { page_size: 30 }) });
export const useFitnessStats = () => useQuery({ queryKey: [...keys.fitness, "stats"], queryFn: () => api.get<FitnessStats>("/fitness/stats/") });

export function useFitnessMutation() {
  const inv = useInvalidate();
  return useMutation({ mutationFn: (fn: () => Promise<unknown>) => fn(), onSuccess: () => inv(keys.fitness, keys.dashboard, keys.insights, keys.reminders) });
}

export const useHydration = () =>
  useQuery({ queryKey: [...keys.wellness, "water"], queryFn: () => api.get<{ today: HydrationDay; week: { date: string; total_ml: number; target_ml: number }[] }>("/wellness/water/summary/") });

export const useSleep = () =>
  useQuery({
    queryKey: [...keys.wellness, "sleep"],
    queryFn: async () => ({
      logs: await api.get<Paginated<SleepLog>>("/wellness/sleep/", { page_size: 14 }),
      summary: await api.get<{ summary: { nights: number; average_minutes: number | null; bedtime_spread_minutes: number | null; average_quality: number | null }; planned: { bedtime: string; wake_time: string } }>("/wellness/sleep/summary/"),
    }),
  });

export const useJournal = (q: string) =>
  useQuery({ queryKey: [...keys.wellness, "journal", q], queryFn: () => api.get<Paginated<JournalEntry>>("/wellness/journal/", { q, page_size: 30 }) });

export const useJournalPrompt = () => useQuery({ queryKey: [...keys.wellness, "prompt"], queryFn: () => api.get<{ prompt: string }>("/wellness/journal/prompt/") });

export const useMindfulness = () =>
  useQuery({ queryKey: [...keys.wellness, "mindfulness"], queryFn: () => api.get<Paginated<MindfulnessSession>>("/wellness/mindfulness/", { page_size: 10 }) });

export function useWellnessMutation() {
  const inv = useInvalidate();
  return useMutation({ mutationFn: (fn: () => Promise<unknown>) => fn(), onSuccess: () => inv(keys.wellness, keys.dashboard, keys.reminders) });
}
