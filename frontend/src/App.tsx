import { lazy, Suspense, type ReactNode } from "react";
import { Route, Routes } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import { QuickAddProvider } from "./components/layout/QuickAddContext";
import { LoadingList } from "./components/ui/feedback";
import { AlarmProvider } from "./features/alarms/AlarmProvider";
import { GuestOnly, RequireAuth } from "./features/auth/session";

const Login = lazy(() => import("./pages/auth/Login"));
const Register = lazy(() => import("./pages/auth/Register"));
const ForgotPassword = lazy(() => import("./pages/auth/ForgotPassword"));
const ResetPassword = lazy(() => import("./pages/auth/ResetPassword"));
const VerifyEmail = lazy(() => import("./pages/auth/VerifyEmail"));
const Onboarding = lazy(() => import("./pages/Onboarding"));
const Today = lazy(() => import("./pages/Today"));
const Calendar = lazy(() => import("./pages/Calendar"));
const Tasks = lazy(() => import("./pages/Tasks"));
const Habits = lazy(() => import("./pages/Habits"));
const Growth = lazy(() => import("./pages/growth/Growth"));
const Insights = lazy(() => import("./pages/Insights"));
const Settings = lazy(() => import("./pages/settings/Settings"));
const Notifications = lazy(() => import("./pages/Notifications"));
const Reminders = lazy(() => import("./pages/Reminders"));
const NotFound = lazy(() => import("./pages/NotFound"));

function Page({ children }: { children: ReactNode }) {
  return <Suspense fallback={<div className="p-4"><LoadingList rows={4} /></div>}>{children}</Suspense>;
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<GuestOnly><Page><Login /></Page></GuestOnly>} />
      <Route path="/register" element={<GuestOnly><Page><Register /></Page></GuestOnly>} />
      <Route path="/forgot-password" element={<Page><ForgotPassword /></Page>} />
      <Route path="/reset-password" element={<Page><ResetPassword /></Page>} />
      <Route path="/verify-email" element={<Page><VerifyEmail /></Page>} />
      <Route path="/welcome" element={<RequireAuth allowOnboarding><Page><Onboarding /></Page></RequireAuth>} />
      <Route
        element={
          <RequireAuth>
            <AlarmProvider>
              <QuickAddProvider>
                <AppShell />
              </QuickAddProvider>
            </AlarmProvider>
          </RequireAuth>
        }
      >
        <Route index element={<Page><Today /></Page>} />
        <Route path="calendar" element={<Page><Calendar /></Page>} />
        <Route path="tasks" element={<Page><Tasks /></Page>} />
        <Route path="habits" element={<Page><Habits /></Page>} />
        <Route path="growth/*" element={<Page><Growth /></Page>} />
        <Route path="insights" element={<Page><Insights /></Page>} />
        <Route path="settings/*" element={<Page><Settings /></Page>} />
        <Route path="notifications" element={<Page><Notifications /></Page>} />
        <Route path="reminders" element={<Page><Reminders /></Page>} />
        <Route path="*" element={<Page><NotFound /></Page>} />
      </Route>
    </Routes>
  );
}
