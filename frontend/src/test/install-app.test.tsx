import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { InstallApp } from "@/components/InstallApp";
import { resetInstallState } from "@/lib/install";
import { renderApp } from "./utils";

function fireInstallable(outcome: "accepted" | "dismissed" = "accepted") {
  const event = Object.assign(new Event("beforeinstallprompt", { cancelable: true }), {
    prompt: vi.fn(async () => undefined),
    userChoice: Promise.resolve({ outcome }),
  });
  act(() => { window.dispatchEvent(event); });
  return event;
}

afterEach(() => {
  vi.unstubAllGlobals();
  act(() => resetInstallState());
});

describe("Install app button", () => {
  it("is hidden until the browser says DayWell is installable", () => {
    vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
    renderApp(<InstallApp />);
    expect(screen.queryByRole("button", { name: /Install app/ })).not.toBeInTheDocument();
  });
});

describe("Install app button flows", () => {
  it("uses DayWell's own button: suppresses Chrome's infobar and opens the install dialog", async () => {
    vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
    renderApp(<InstallApp />);
    const event = fireInstallable("accepted");
    expect(event.defaultPrevented).toBe(true);
    await userEvent.click(await screen.findByRole("button", { name: /Install app/ }));
    expect(event.prompt).toHaveBeenCalledOnce();
    await waitFor(() => expect(screen.queryByRole("button", { name: /Install app/ })).not.toBeInTheDocument());
    expect(await screen.findByText("DayWell is installing")).toBeInTheDocument();
  });

  it("on iPhone Safari shows Add to Home Screen steps", async () => {
    vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
    vi.stubGlobal("navigator", { ...navigator, userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1", maxTouchPoints: 5 });
    renderApp(<InstallApp />);
    await userEvent.click(screen.getByRole("button", { name: /Install app/ }));
    expect(await screen.findByText(/Add to Home Screen/)).toBeInTheDocument();
  });

  it("renders nothing once running as the installed app", async () => {
    vi.stubGlobal("matchMedia", (q: string) => ({ matches: q.includes("standalone"), addEventListener() {}, removeEventListener() {} }));
    renderApp(<InstallApp />);
    fireInstallable();
    expect(screen.queryByRole("button", { name: /Install/ })).not.toBeInTheDocument();
  });
});
