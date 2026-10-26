import type { ReactNode } from "react";
import { InstallApp } from "@/components/InstallApp";

export function AuthLayout({ title, subtitle, children, footer }: { title: string; subtitle?: string; children: ReactNode; footer?: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center px-4 py-10">
      <main className="w-full max-w-md">
        <div className="mb-6 flex flex-col items-center text-center">
          <img src="/icons/icon-192.png" alt="" className="mb-3 h-14 w-14 rounded-2xl shadow-sm" />
          <p className="font-[family-name:var(--font-display)] text-2xl font-semibold text-primary-strong">DayWell</p>
          <h1 className="mt-4 text-xl font-semibold">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
        </div>
        <div className="rounded-[var(--radius-card)] border border-line bg-surface p-5 shadow-[var(--shadow-card)] sm:p-6">{children}</div>
        {footer && <div className="mt-5 text-center text-sm text-muted">{footer}</div>}
        <div className="mt-6"><InstallApp /></div>
      </main>
    </div>
  );
}
