"use client";

import Image from "next/image";
import {
  AlertTriangle,
  ArrowLeft,
  Bell,
  Building2,
  CheckCircle2,
  CircleDot,
  Clock3,
  Headphones,
  KeyRound,
  LayoutDashboard,
  MessageSquareText,
  ReceiptText,
  Search,
  Store as StoreIcon,
  Trash2,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:5000";
const DASHBOARD_AUTH_USER = process.env.NEXT_PUBLIC_DASHBOARD_AUTH_USER;
const DASHBOARD_AUTH_PASS = process.env.NEXT_PUBLIC_DASHBOARD_AUTH_PASS;
const REFRESH_MS = 8000;

type Store = {
  id: number;
  name: string;
  slug?: string;
  created_at?: string;
};

type Salesperson = {
  id: number;
  store_id: number;
  name: string;
  designation: string;
  pin_set?: boolean;
  is_active?: number | boolean;
  created_at?: string;
};

type DashboardView = "stores" | "pin-management";

type Session = {
  salesperson_name?: string;
  session_id: string;
  store_id?: number | null;
  salesperson_id?: number | null;
  start_time?: string;
  end_time?: string | null;
  is_active?: boolean;
};

type SessionEvent = {
  id?: number;
  timestamp?: string;
  transcript?: string;
  alert_priority?: string;
  reasoning?: string;
  manager_feedback?: FeedbackValue | null;
};

type FeedbackValue = "useful" | "false_alarm" | "noted";

type Stats = {
  total_events: number;
  alerts_fired: number;
  objections: number;
  price_concerns: number;
  certification_questions: number;
  upsell_misses: number;
  high_intent_signals: number;
};

type SalespersonSummary = {
  sessionCountToday: number;
  activeSessionCount: number;
  lastAlertTime: string | null;
};

const emptyStats: Stats = {
  total_events: 0,
  alerts_fired: 0,
  objections: 0,
  price_concerns: 0,
  certification_questions: 0,
  upsell_misses: 0,
  high_intent_signals: 0,
};

const primaryStatCards: Array<{
  key: keyof Stats;
  label: string;
  icon: LucideIcon;
}> = [
    { key: "total_events", label: "Total Events", icon: MessageSquareText },
    { key: "alerts_fired", label: "Alerts", icon: Zap },
    { key: "objections", label: "Objections", icon: AlertTriangle },
    { key: "price_concerns", label: "Price Concerns", icon: ReceiptText },
  ];

const signalRows: Array<{
  key: keyof Stats;
  label: string;
  tone: string;
}> = [
    { key: "certification_questions", label: "Certification Questions", tone: "bg-amber-300" },
    { key: "upsell_misses", label: "Upsell Misses", tone: "bg-orange-300" },
    { key: "high_intent_signals", label: "Intent Signals", tone: "bg-emerald-300" },
  ];

const feedbackOptions: Array<{ value: FeedbackValue; label: string }> = [
  { value: "useful", label: "Useful" },
  { value: "false_alarm", label: "False Alarm" },
  { value: "noted", label: "Noted" },
];

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }

  return response.json();
}

function fetchStores() {
  return fetchJson<Store[]>(`${API_BASE}/api/stores`);
}

function fetchStoreSalespersons(storeId: number) {
  return fetchJson<Salesperson[]>(
    `${API_BASE}/api/stores/${encodeURIComponent(storeId)}/salespersons`,
  );
}

function basicAuthHeader(): Record<string, string> {
  if (!DASHBOARD_AUTH_USER || !DASHBOARD_AUTH_PASS) {
    return {};
  }

  return {
    Authorization: `Basic ${window.btoa(`${DASHBOARD_AUTH_USER}:${DASHBOARD_AUTH_PASS}`)}`,
  };
}

async function setSalespersonPin(salespersonId: number, pin: string) {
  const response = await fetch(`${API_BASE}/api/admin/set_pin`, {
    method: "POST",
    credentials: "include",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...basicAuthHeader(),
    },
    body: JSON.stringify({ salesperson_id: salespersonId, pin }),
  });

  const payload = await response.json().catch(() => null) as { error?: string } | null;

  if (!response.ok) {
    throw new Error(payload?.error ?? `${response.status} ${response.statusText}`);
  }

  return payload;
}

function fetchSessions(storeId?: number) {
  const query = storeId ? `?store_id=${encodeURIComponent(storeId)}` : "";
  return fetchJson<Session[]>(`${API_BASE}/api/sessions${query}`);
}

function fetchEvents(sessionId: string) {
  return fetchJson<SessionEvent[]>(
    `${API_BASE}/api/events/${encodeURIComponent(sessionId)}`,
  );
}

function fetchStats(sessionId: string) {
  return fetchJson<Stats>(`${API_BASE}/api/stats/${encodeURIComponent(sessionId)}`);
}

async function deleteSession(sessionId: string) {
  const response = await fetch(
    `${API_BASE}/api/sessions/${encodeURIComponent(sessionId)}`,
    {
      method: "DELETE",
      credentials: "include",
      headers: {
        Accept: "application/json",
        ...basicAuthHeader(),
      },
    },
  );

  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
}

function isActiveSession(session: Session) {
  if (typeof session.is_active === "boolean") {
    return session.is_active;
  }

  return !session.end_time;
}

function isToday(value?: string) {
  if (!value) {
    return false;
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return false;
  }

  const now = new Date();
  return (
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate()
  );
}

function formatTimestamp(value?: string | null) {
  if (!value) {
    return "No timestamp";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatDuration(start?: string, end?: string | null) {
  if (!start) {
    return "Not started";
  }

  const startDate = new Date(start);
  const endDate = end ? new Date(end) : new Date();
  if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) {
    return "Unknown";
  }

  const totalMinutes = Math.max(0, Math.round((endDate.getTime() - startDate.getTime()) / 60000));
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
}

function normalizePriority(priority?: string) {
  const value = String(priority || "none").toLowerCase();
  return ["high", "medium", "low", "none"].includes(value) ? value : "none";
}

function priorityClasses(priority?: string) {
  switch (normalizePriority(priority)) {
    case "high":
      return "border-red-400/35 bg-red-500/15 text-red-100";
    case "medium":
      return "border-amber-300/35 bg-amber-400/15 text-amber-100";
    case "low":
      return "border-[var(--mk-gold)]/30 bg-[var(--mk-gold)]/10 text-[var(--mk-gold-light)]";
    default:
      return "border-white/10 bg-white/5 text-zinc-300";
  }
}

function priorityDotClasses(priority?: string) {
  switch (normalizePriority(priority)) {
    case "high":
      return "bg-red-400 shadow-[0_0_14px_rgba(248,113,113,0.55)]";
    case "medium":
      return "bg-amber-300 shadow-[0_0_14px_rgba(252,211,77,0.35)]";
    case "low":
      return "bg-[var(--mk-gold-light)]";
    default:
      return "bg-zinc-500";
  }
}

function signalBadges(event: SessionEvent) {
  const text = `${event.reasoning ?? ""} ${event.transcript ?? ""}`.toLowerCase();
  const badges: Array<{ label: string; className: string }> = [];

  if (normalizePriority(event.alert_priority) === "high") {
    badges.push({ label: "Priority", className: "border-red-400/30 bg-red-500/10 text-red-100" });
  }
  if (text.includes("objection")) {
    badges.push({ label: "Objection", className: "border-red-400/30 bg-red-500/10 text-red-100" });
  }
  if (text.includes("price")) {
    badges.push({ label: "Price Concern", className: "border-amber-300/30 bg-amber-400/10 text-amber-100" });
  }
  if (text.includes("intent")) {
    badges.push({ label: "Intent Signal", className: "border-emerald-300/30 bg-emerald-400/10 text-emerald-100" });
  }

  return badges.length > 0
    ? badges
    : [{ label: "Conversation", className: "border-white/10 bg-white/5 text-zinc-300" }];
}

function sessionBelongsToSalesperson(session: Session, salesperson: Salesperson) {
  if (session.salesperson_id && session.salesperson_id === salesperson.id) {
    return true;
  }

  return session.salesperson_name === salesperson.name;
}

function newestSessionForSalesperson(
  sessions: Session[],
  salesperson: Salesperson | null,
) {
  if (!salesperson) {
    return null;
  }

  return (
    sessions.find((session) => sessionBelongsToSalesperson(session, salesperson)) ?? null
  );
}

function buildSalespersonSummary(
  sessions: Session[],
  salesperson: Salesperson,
  lastAlertTime: string | null,
): SalespersonSummary {
  const matchingSessions = sessions.filter((session) =>
    sessionBelongsToSalesperson(session, salesperson),
  );
  const todaySessions = matchingSessions.filter((session) => isToday(session.start_time));

  return {
    sessionCountToday: todaySessions.length,
    activeSessionCount: todaySessions.filter(isActiveSession).length,
    lastAlertTime,
  };
}

async function loadLastAlertTimes(
  sessions: Session[],
  salespersons: Salesperson[],
): Promise<Record<number, string | null>> {
  const latestSessions = salespersons.map((salesperson) => ({
    salesperson,
    session: newestSessionForSalesperson(sessions, salesperson),
  }));

  const entries = await Promise.all(
    latestSessions.map(async ({ salesperson, session }) => {
      if (!session) {
        return [salesperson.id, null] as const;
      }

      const events = await fetchEvents(session.session_id);
      const alert = events.find((event) =>
        ["medium", "high"].includes(normalizePriority(event.alert_priority)),
      );

      return [salesperson.id, alert?.timestamp ?? null] as const;
    }),
  );

  return Object.fromEntries(entries);
}

function useIstTime() {
  const [time, setTime] = useState("");

  useEffect(() => {
    const update = () => {
      setTime(
        new Intl.DateTimeFormat("en-IN", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          timeZone: "Asia/Kolkata",
        }).format(new Date()),
      );
    };

    update();
    const interval = window.setInterval(update, 1000);
    return () => window.clearInterval(interval);
  }, []);

  return time;
}

export default function Page() {
  const [view, setView] = useState<DashboardView>("stores");
  const [stores, setStores] = useState<Store[]>([]);
  const [allSessions, setAllSessions] = useState<Session[]>([]);
  const [storeSessions, setStoreSessions] = useState<Session[]>([]);
  const [salespersons, setSalespersons] = useState<Salesperson[]>([]);
  const [salespersonSummaries, setSalespersonSummaries] = useState<
    Record<number, SalespersonSummary>
  >({});
  const [selectedStore, setSelectedStore] = useState<Store | null>(null);
  const [selectedSalesperson, setSelectedSalesperson] = useState<Salesperson | null>(
    null,
  );
  const [selectedSession, setSelectedSession] = useState<Session | null>(null);
  const [sessionSelectionPaused, setSessionSelectionPaused] = useState(false);
  const [events, setEvents] = useState<SessionEvent[]>([]);
  const [savedFeedbackIds, setSavedFeedbackIds] = useState<Set<number>>(
    () => new Set(),
  );
  const [stats, setStats] = useState<Stats>(emptyStats);
  const [isLoadingStores, setIsLoadingStores] = useState(true);
  const [isLoadingSalespersons, setIsLoadingSalespersons] = useState(false);
  const [isLoadingConversation, setIsLoadingConversation] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const loadStores = useCallback(async () => {
    setError(null);
    setIsLoadingStores(true);

    try {
      const [nextStores, nextSessions] = await Promise.all([
        fetchStores(),
        fetchSessions(),
      ]);

      setStores(nextStores);
      setAllSessions(nextSessions);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Store refresh failed");
    } finally {
      setIsLoadingStores(false);
    }
  }, []);

  const loadSalespersons = useCallback(async (store: Store) => {
    setError(null);
    setIsLoadingSalespersons(true);

    try {
      const [nextSalespersons, nextSessions] = await Promise.all([
        fetchStoreSalespersons(store.id),
        fetchSessions(store.id),
      ]);
      const lastAlertTimes = await loadLastAlertTimes(nextSessions, nextSalespersons);

      setSalespersons(nextSalespersons);
      setStoreSessions(nextSessions);
      setSalespersonSummaries(
        Object.fromEntries(
          nextSalespersons.map((salesperson) => [
            salesperson.id,
            buildSalespersonSummary(
              nextSessions,
              salesperson,
              lastAlertTimes[salesperson.id] ?? null,
            ),
          ]),
        ),
      );
    } catch (loadError) {
      setError(
        loadError instanceof Error ? loadError.message : "Salesperson refresh failed",
      );
    } finally {
      setIsLoadingSalespersons(false);
    }
  }, []);

  const loadConversation = useCallback(async () => {
    if (!selectedStore || !selectedSalesperson) {
      return;
    }

    setError(null);
    setIsLoadingConversation(true);

    try {
      const nextSessions = await fetchSessions(selectedStore.id);
      const nextSelectedSession = selectedSession
        ? nextSessions.find(
          (session) => session.session_id === selectedSession.session_id,
        ) ?? null
        : sessionSelectionPaused
          ? null
          : newestSessionForSalesperson(nextSessions, selectedSalesperson);

      setStoreSessions(nextSessions);
      setSelectedSession(nextSelectedSession);

      if (!nextSelectedSession) {
        setEvents([]);
        setStats(emptyStats);
        setLastUpdated(new Date());
        return;
      }

      const [nextEvents, nextStats] = await Promise.all([
        fetchEvents(nextSelectedSession.session_id),
        fetchStats(nextSelectedSession.session_id),
      ]);

      setEvents(nextEvents);
      setStats({ ...emptyStats, ...nextStats });
      setLastUpdated(new Date());
    } catch (loadError) {
      setError(
        loadError instanceof Error ? loadError.message : "Conversation refresh failed",
      );
    } finally {
      setIsLoadingConversation(false);
    }
  }, [selectedSalesperson, selectedSession, selectedStore, sessionSelectionPaused]);

  useEffect(() => {
    const initialRefresh = window.setTimeout(() => void loadStores(), 0);

    return () => {
      window.clearTimeout(initialRefresh);
    };
  }, [loadStores]);

  useEffect(() => {
    if (!selectedStore || selectedSalesperson) {
      return;
    }

    const initialRefresh = window.setTimeout(
      () => void loadSalespersons(selectedStore),
      0,
    );

    return () => {
      window.clearTimeout(initialRefresh);
    };
  }, [loadSalespersons, selectedSalesperson, selectedStore]);

  useEffect(() => {
    if (!selectedStore || !selectedSalesperson) {
      return;
    }

    const initialRefresh = window.setTimeout(() => void loadConversation(), 0);
    const interval = window.setInterval(() => void loadConversation(), REFRESH_MS);

    return () => {
      window.clearTimeout(initialRefresh);
      window.clearInterval(interval);
    };
  }, [loadConversation, selectedSalesperson, selectedStore]);

  const storeActiveCounts = useMemo(() => {
    const counts = new Map<number, number>();

    allSessions.forEach((session) => {
      if (!session.store_id || !isToday(session.start_time) || !isActiveSession(session)) {
        return;
      }

      counts.set(session.store_id, (counts.get(session.store_id) ?? 0) + 1);
    });

    return counts;
  }, [allSessions]);

  const saveFeedback = useCallback(
    async (eventId: number, feedback: FeedbackValue) => {
      const response = await fetch(`${API_BASE}/api/feedback/${eventId}`, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ feedback }),
      });

      if (!response.ok) {
        throw new Error(`${response.status} ${response.statusText}`);
      }

      setSavedFeedbackIds((previous) => new Set(previous).add(eventId));
      setEvents((previous) =>
        previous.map((event) =>
          event.id === eventId ? { ...event, manager_feedback: feedback } : event,
        ),
      );
    },
    [],
  );

  const selectSession = useCallback(async (session: Session) => {
    setError(null);
    setIsLoadingConversation(true);
    setSelectedSession(session);
    setSessionSelectionPaused(false);

    try {
      const [nextEvents, nextStats] = await Promise.all([
        fetchEvents(session.session_id),
        fetchStats(session.session_id),
      ]);

      setEvents(nextEvents);
      setStats({ ...emptyStats, ...nextStats });
      setLastUpdated(new Date());
    } catch (loadError) {
      setError(
        loadError instanceof Error ? loadError.message : "Conversation refresh failed",
      );
    } finally {
      setIsLoadingConversation(false);
    }
  }, []);

  const removeDeletedSession = useCallback(
    async (sessionId: string) => {
      await deleteSession(sessionId);

      setAllSessions((previous) =>
        previous.filter((session) => session.session_id !== sessionId),
      );
      setStoreSessions((previous) =>
        previous.filter((session) => session.session_id !== sessionId),
      );

      if (selectedSession?.session_id === sessionId) {
        setSelectedSession(null);
        setSessionSelectionPaused(true);
        setEvents([]);
        setStats(emptyStats);
        setLastUpdated(new Date());
      }
    },
    [selectedSession],
  );

  const selectStore = (store: Store) => {
    setView("stores");
    setSelectedStore(store);
    setSelectedSalesperson(null);
    setSelectedSession(null);
    setSessionSelectionPaused(false);
    setEvents([]);
    setStats(emptyStats);
    setLastUpdated(null);
  };

  const selectSalesperson = (salesperson: Salesperson) => {
    setSelectedSalesperson(salesperson);
    setSelectedSession(null);
    setSessionSelectionPaused(false);
  };

  const backToStores = () => {
    setView("stores");
    setSelectedStore(null);
    setSelectedSalesperson(null);
    setSelectedSession(null);
    setSessionSelectionPaused(false);
    setSalespersons([]);
    setStoreSessions([]);
    setEvents([]);
    setStats(emptyStats);
    setLastUpdated(null);
    void loadStores();
  };

  const openPinManagement = () => {
    setView("pin-management");
    setError(null);
  };

  const backToSalespersons = () => {
    setSelectedSalesperson(null);
    setSelectedSession(null);
    setSessionSelectionPaused(false);
    setEvents([]);
    setStats(emptyStats);
    setLastUpdated(null);
    if (selectedStore) {
      void loadSalespersons(selectedStore);
    }
  };

  const activeSessions = allSessions.filter(
    (session) => isToday(session.start_time) && isActiveSession(session),
  ).length;

  return (
    <main className="min-h-screen overflow-x-hidden bg-[var(--mk-dark)] text-[var(--mk-text-on-dark)]">
      <div className="flex min-h-screen w-full flex-col lg:flex-row">
        <DashboardSidebar
          activeSessions={activeSessions}
          activeView={view}
          onSelectPinManagement={openPinManagement}
          onSelectStores={backToStores}
          selectedSalesperson={selectedSalesperson}
          selectedStore={selectedStore}
        />

        <div className="min-w-0 flex-1">
          <DashboardTopbar
            activeSessions={activeSessions}
            activeView={view}
            lastUpdated={lastUpdated}
            selectedSalesperson={selectedSalesperson}
            selectedSession={selectedSession}
            selectedStore={selectedStore}
          />

          <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-5 px-4 py-5 sm:px-6 lg:px-8">
            {error ? (
              <div className="rounded-lg border border-red-400/25 bg-red-500/10 p-3 text-sm text-red-100">
                Could not refresh dashboard: {error}
              </div>
            ) : null}

            {view === "pin-management" ? (
              <PinManagementView stores={stores} />
            ) : !selectedStore ? (
              <StoreSelection
                activeCounts={storeActiveCounts}
                isLoading={isLoadingStores}
                onSelectStore={selectStore}
                stores={stores}
              />
            ) : !selectedSalesperson ? (
              <SalespersonSelection
                isLoading={isLoadingSalespersons}
                onBack={backToStores}
                onSelectSalesperson={selectSalesperson}
                salespersons={salespersons}
                store={selectedStore}
                summaries={salespersonSummaries}
              />
            ) : (
              <ConversationView
                events={events}
                isLoading={isLoadingConversation}
                lastUpdated={lastUpdated}
                onBack={backToSalespersons}
                onDeleteSession={removeDeletedSession}
                onSaveFeedback={saveFeedback}
                onSelectSession={selectSession}
                savedFeedbackIds={savedFeedbackIds}
                salesperson={selectedSalesperson}
                selectedSession={selectedSession}
                stats={stats}
                store={selectedStore}
                storeSessions={storeSessions}
              />
            )}
          </div>
        </div>
      </div>
    </main>
  );
}

function DashboardSidebar({
  activeSessions,
  activeView,
  onSelectPinManagement,
  onSelectStores,
  selectedSalesperson,
  selectedStore,
}: {
  activeSessions: number;
  activeView: DashboardView;
  onSelectPinManagement: () => void;
  onSelectStores: () => void;
  selectedSalesperson: Salesperson | null;
  selectedStore: Store | null;
}) {
  const navItems = [
    { label: "Stores", icon: StoreIcon, active: activeView === "stores" && !selectedStore, action: onSelectStores },
    {
      label: "Live Sessions",
      icon: Headphones,
      active: activeView === "stores" && Boolean(selectedStore),
      action: activeView === "stores" && selectedStore ? undefined : onSelectStores,
    },
    { label: "PIN Management", icon: KeyRound, active: activeView === "pin-management", action: onSelectPinManagement },
    { label: "Reports", icon: LayoutDashboard, active: false },
    { label: "Alerts Log", icon: Bell, active: false },
  ];

  return (
    <aside className="border-b border-white/10 bg-black/70 lg:sticky lg:top-0 lg:h-screen lg:w-72 lg:border-b-0 lg:border-r">
      <div className="flex h-full flex-col gap-5 p-4 lg:p-5">
        <div className="flex items-center justify-between gap-4 lg:block">
          <div className="relative h-10 w-40 overflow-hidden rounded-md border border-[var(--mk-gold)]/20 bg-black lg:h-14 lg:w-full">
            <Image
              src="/brand/mk-jewels-dark.jpeg"
              alt="MK Jewels"
              fill
              sizes="(min-width: 1024px) 240px, 160px"
              className="object-contain"
              priority
            />
          </div>
          <div className="flex items-center gap-2 rounded-full border border-emerald-300/20 bg-emerald-400/10 px-3 py-1.5 text-xs text-emerald-100 lg:mt-5 lg:w-fit">
            <span className="size-2 rounded-full bg-emerald-300 shadow-[0_0_14px_rgba(110,231,183,0.65)]" />
            {activeSessions} live
          </div>
        </div>

        <nav className="grid grid-cols-2 gap-2 lg:flex lg:flex-col" aria-label="Dashboard navigation">
          {navItems.map(({ label, icon: Icon, active, action }) => (
            <button
              key={label}
              type="button"
              onClick={action}
              className={cn(
                "flex min-h-11 items-center gap-3 rounded-lg border px-3.5 py-2.5 text-sm font-medium transition",
                active
                  ? "border-[var(--mk-gold)]/45 bg-[var(--mk-gold)]/12 text-[var(--mk-gold-light)]"
                  : "border-transparent text-zinc-400 hover:border-white/10 hover:bg-white/[0.04] hover:text-zinc-100",
                !action && !active ? "cursor-default opacity-70" : "",
              )}
            >
              <Icon className="size-4" />
              <span>{label}</span>
            </button>
          ))}
        </nav>

        <div className="mt-auto hidden rounded-lg border border-[var(--mk-gold)]/15 bg-[var(--mk-surface)] p-4 lg:block">
          <p className="text-xs uppercase tracking-[0.18em] text-[var(--mk-gold)]">
            Current View
          </p>
          <p className="mt-2 text-sm font-medium text-zinc-100">
            {activeView === "pin-management"
              ? "Salesperson PINs"
              : selectedSalesperson?.name ?? selectedStore?.name ?? "Store Overview"}
          </p>
          <p className="mt-1 text-xs leading-5 text-zinc-500">
            Live monitoring for sales floor conversations and manager feedback.
          </p>
        </div>
      </div>
    </aside>
  );
}

function DashboardTopbar({
  activeSessions,
  activeView,
  lastUpdated,
  selectedSalesperson,
  selectedSession,
  selectedStore,
}: {
  activeSessions: number;
  activeView: DashboardView;
  lastUpdated: Date | null;
  selectedSalesperson: Salesperson | null;
  selectedSession: Session | null;
  selectedStore: Store | null;
}) {
  const istTime = useIstTime();
  const breadcrumb = activeView === "pin-management"
    ? ["PIN Management"]
    : [
      selectedStore?.name ?? "Stores",
      selectedSalesperson?.name,
      selectedSession ? `Session #${selectedSession.session_id}` : selectedSalesperson ? "No session" : undefined,
    ].filter(Boolean);

  return (
    <header className="border-b border-white/10 bg-[rgba(10,10,10,0.88)] px-4 py-4 backdrop-blur sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-[1400px] flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="min-w-0">
          <p className="truncate text-sm text-zinc-400">{breadcrumb.join(" > ")}</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-zinc-50">
            {activeView === "pin-management"
              ? "PIN Management"
              : selectedSalesperson ? "Conversation Monitor" : selectedStore ? "Sales Team" : "Store Overview"}
          </h1>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-400">
          <span className="inline-flex min-h-9 items-center gap-2 rounded-full border border-emerald-300/20 bg-emerald-400/10 px-3 text-emerald-100">
            <span className="mk-live-pulse size-2 rounded-full bg-emerald-300" />
            {activeSessions} active
          </span>
          <span className="inline-flex min-h-9 items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3">
            <Clock3 className="size-3.5 text-[var(--mk-gold)]" />
            {istTime || "IST"}
          </span>
          {lastUpdated ? (
            <span className="inline-flex min-h-9 items-center rounded-full border border-white/10 bg-white/[0.04] px-3">
              Updated {lastUpdated.toLocaleTimeString()}
            </span>
          ) : null}
        </div>
      </div>
    </header>
  );
}

function StoreSelection({
  activeCounts,
  isLoading,
  onSelectStore,
  stores,
}: {
  activeCounts: Map<number, number>;
  isLoading: boolean;
  onSelectStore: (store: Store) => void;
  stores: Store[];
}) {
  return (
    <section className="flex flex-col gap-5">
      <SectionIntro
        eyebrow="Stores"
        title="Choose a location"
        description="Start with the store floor you want to review."
      />

      {isLoading && stores.length === 0 ? (
        <EmptyState>Loading stores</EmptyState>
      ) : stores.length === 0 ? (
        <EmptyState>No stores found.</EmptyState>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {stores.map((store) => {
            const activeCount = activeCounts.get(store.id) ?? 0;
            const isPrimaryStore = store.name.toLowerCase().includes("bandra");

            return (
              <button
                key={store.id}
                type="button"
                onClick={() => onSelectStore(store)}
                className={cn(
                  "group min-h-44 rounded-lg border bg-[var(--mk-surface)] p-5 text-left transition hover:-translate-y-0.5 hover:border-[var(--mk-gold)]/65 hover:bg-[#202020] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--mk-gold)]/70",
                  isPrimaryStore ? "border-[var(--mk-gold)]/22" : "border-white/10 opacity-75",
                )}
              >
                <div className="flex h-full flex-col justify-between gap-6">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex size-11 items-center justify-center rounded-lg border border-[var(--mk-gold)]/20 bg-[var(--mk-gold)]/10 text-[var(--mk-gold)]">
                      <Building2 className="size-5" />
                    </div>
                    <Badge className={cn(
                      "border-white/10 bg-white/[0.04] text-zinc-300",
                      !isPrimaryStore ? "border-[var(--mk-gold)]/25 text-[var(--mk-gold-light)]" : "",
                    )}>
                      {isPrimaryStore ? "Open" : "Coming Soon"}
                    </Badge>
                  </div>
                  <div>
                    <h2 className="text-2xl font-semibold text-zinc-50">{store.name}</h2>
                    <p className="mt-2 text-sm text-zinc-500">
                      {activeCount} active session{activeCount === 1 ? "" : "s"} today
                    </p>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}

function SalespersonSelection({
  isLoading,
  onBack,
  onSelectSalesperson,
  salespersons,
  store,
  summaries,
}: {
  isLoading: boolean;
  onBack: () => void;
  onSelectSalesperson: (salesperson: Salesperson) => void;
  salespersons: Salesperson[];
  store: Store;
  summaries: Record<number, SalespersonSummary>;
}) {
  const [query, setQuery] = useState("");
  const filteredSalespersons = salespersons.filter((salesperson) => {
    const needle = query.trim().toLowerCase();
    if (!needle) {
      return true;
    }

    return `${salesperson.name} ${salesperson.designation}`.toLowerCase().includes(needle);
  });

  return (
    <section className="flex flex-col gap-5">
      <ViewHeader onBack={onBack} subtitle="Store" title={store.name} />

      <div className="flex flex-col gap-3 rounded-lg border border-white/10 bg-[var(--mk-surface)] p-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.18em] text-[var(--mk-gold)]">
            Sales Team
          </p>
          <p className="mt-1 text-sm text-zinc-400">
            Select a salesperson to open the latest live conversation.
          </p>
        </div>
        <label className="relative w-full sm:max-w-xs">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-zinc-500" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search salesperson"
            className="h-11 w-full rounded-lg border border-white/10 bg-black/25 pl-9 pr-3 text-sm text-zinc-100 outline-none transition placeholder:text-zinc-600 focus:border-[var(--mk-gold)]/60 focus:ring-2 focus:ring-[var(--mk-gold)]/15"
            type="search"
          />
        </label>
      </div>

      {isLoading && salespersons.length === 0 ? (
        <EmptyState>Loading salespeople</EmptyState>
      ) : salespersons.length === 0 ? (
        <EmptyState>No salespeople found for this store.</EmptyState>
      ) : filteredSalespersons.length === 0 ? (
        <EmptyState>No salespeople match this search.</EmptyState>
      ) : (
        <div className="overflow-hidden rounded-lg border border-white/10 bg-[var(--mk-surface)]">
          <div className="hidden grid-cols-[1.4fr_1fr_0.8fr_1fr] gap-4 border-b border-white/10 px-4 py-3 text-xs uppercase tracking-[0.14em] text-zinc-500 md:grid">
            <span>Name</span>
            <span>Designation</span>
            <span>Status</span>
            <span>Last Active</span>
          </div>
          <div className="divide-y divide-white/10">
            {filteredSalespersons.map((salesperson) => {
              const summary = summaries[salesperson.id] ?? {
                activeSessionCount: 0,
                lastAlertTime: null,
                sessionCountToday: 0,
              };
              const isActive = summary.activeSessionCount > 0;

              return (
                <button
                  key={salesperson.id}
                  type="button"
                  onClick={() => onSelectSalesperson(salesperson)}
                  className="grid w-full gap-3 px-4 py-4 text-left transition hover:bg-white/[0.035] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--mk-gold)]/60 md:grid-cols-[1.4fr_1fr_0.8fr_1fr] md:items-center"
                >
                  <div className="min-w-0">
                    <p className="truncate text-base font-semibold text-zinc-50">
                      {salesperson.name}
                    </p>
                    <p className="mt-1 text-xs text-zinc-500 md:hidden">
                      {salesperson.designation}
                    </p>
                  </div>
                  <p className="hidden text-sm text-zinc-400 md:block">
                    {salesperson.designation}
                  </p>
                  <StatusBadge active={isActive} />
                  <p className="text-sm text-zinc-400">
                    {summary.lastAlertTime ? formatTimestamp(summary.lastAlertTime) : "No alerts today"}
                  </p>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}

function PinManagementView({ stores }: { stores: Store[] }) {
  const [selectedStoreId, setSelectedStoreId] = useState<string>("all");
  const [pinSalespersons, setPinSalespersons] = useState<Salesperson[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [expandedSalespersonId, setExpandedSalespersonId] = useState<number | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const storeNameById = useMemo(
    () => new Map(stores.map((store) => [store.id, store.name])),
    [stores],
  );

  const loadPinSalespersons = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);

    try {
      const nextSalespersons = selectedStoreId === "all"
        ? (await Promise.all(stores.map((store) => fetchStoreSalespersons(store.id)))).flat()
        : await fetchStoreSalespersons(Number(selectedStoreId));

      setPinSalespersons(nextSalespersons);
    } catch (loadSalespersonsError) {
      setLoadError(
        loadSalespersonsError instanceof Error
          ? loadSalespersonsError.message
          : "PIN list refresh failed",
      );
    } finally {
      setIsLoading(false);
    }
  }, [selectedStoreId, stores]);

  useEffect(() => {
    if (stores.length === 0) {
      setPinSalespersons([]);
      return;
    }

    const initialRefresh = window.setTimeout(() => void loadPinSalespersons(), 0);
    return () => window.clearTimeout(initialRefresh);
  }, [loadPinSalespersons, stores.length]);

  const savePin = async (salespersonId: number, pin: string) => {
    await setSalespersonPin(salespersonId, pin);
    setPinSalespersons((previous) =>
      previous.map((salesperson) =>
        salesperson.id === salespersonId ? { ...salesperson, pin_set: true } : salesperson,
      ),
    );
    setSuccessMessage("PIN updated");
    setExpandedSalespersonId(null);
    window.setTimeout(() => setSuccessMessage(null), 2400);
  };

  return (
    <section className="flex flex-col gap-5">
      <div className="flex flex-col gap-4 rounded-lg border border-white/10 bg-[var(--mk-surface)] p-5 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.18em] text-[var(--mk-gold)]">
            PIN Management
          </p>
          <h2 className="mt-2 text-3xl font-semibold tracking-tight text-zinc-50">
            Salesperson PINs
          </h2>
          <p className="mt-2 text-sm leading-6 text-zinc-400">
            Set or change the 4-digit PIN for each salesperson.
          </p>
        </div>

        <label className="w-full md:max-w-xs">
          <span className="text-xs uppercase tracking-[0.14em] text-zinc-500">
            Store Filter
          </span>
          <select
            value={selectedStoreId}
            onChange={(event) => {
              setSelectedStoreId(event.target.value);
              setExpandedSalespersonId(null);
              setSuccessMessage(null);
            }}
            className="mt-2 h-11 w-full rounded-lg border border-white/10 bg-black/35 px-3 text-sm text-zinc-100 outline-none transition focus:border-[var(--mk-gold)]/60 focus:ring-2 focus:ring-[var(--mk-gold)]/15"
          >
            <option value="all">All Stores</option>
            {stores.map((store) => (
              <option key={store.id} value={store.id}>
                {store.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {successMessage ? (
        <div className="rounded-lg border border-[var(--mk-success)]/30 bg-[var(--mk-success)]/10 p-3 text-sm text-[var(--mk-text-on-dark)]">
          {successMessage}
        </div>
      ) : null}

      {loadError ? (
        <div className="rounded-lg border border-[var(--mk-danger)]/30 bg-[var(--mk-danger)]/10 p-3 text-sm text-[var(--mk-text-on-dark)]">
          Could not refresh PIN list: {loadError}
        </div>
      ) : null}

      {isLoading && pinSalespersons.length === 0 ? (
        <EmptyState>Loading salesperson PINs</EmptyState>
      ) : stores.length === 0 ? (
        <EmptyState>No stores found.</EmptyState>
      ) : pinSalespersons.length === 0 ? (
        <EmptyState>No salespeople found for this store.</EmptyState>
      ) : (
        <div className="overflow-hidden rounded-lg border border-white/10 bg-[var(--mk-surface)]">
          <div className="hidden grid-cols-[1.25fr_1fr_1fr_0.8fr_0.8fr] gap-4 border-b border-white/10 px-4 py-3 text-xs uppercase tracking-[0.14em] text-zinc-500 lg:grid">
            <span>Name</span>
            <span>Designation</span>
            <span>Store</span>
            <span>PIN Status</span>
            <span>Action</span>
          </div>
          <div className="divide-y divide-white/10">
            {pinSalespersons.map((salesperson) => (
              <div key={salesperson.id}>
                <div className="grid gap-3 px-4 py-4 lg:grid-cols-[1.25fr_1fr_1fr_0.8fr_0.8fr] lg:items-center">
                  <div className="min-w-0">
                    <p className="truncate text-base font-semibold text-zinc-50">
                      {salesperson.name}
                    </p>
                    <p className="mt-1 text-xs text-zinc-500 lg:hidden">
                      {salesperson.designation}
                    </p>
                  </div>
                  <p className="text-sm text-zinc-400">{salesperson.designation}</p>
                  <p className="text-sm text-zinc-400">
                    {storeNameById.get(salesperson.store_id) ?? "Unknown Store"}
                  </p>
                  <PinStatusBadge pinSet={Boolean(salesperson.pin_set)} />
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => {
                      setExpandedSalespersonId((current) =>
                        current === salesperson.id ? null : salesperson.id,
                      );
                      setSuccessMessage(null);
                    }}
                    className="min-h-10 w-fit border-[var(--mk-gold)]/35 bg-transparent text-[var(--mk-gold-light)] hover:border-[var(--mk-gold)]/65 hover:bg-[var(--mk-gold)]/10 hover:text-[var(--mk-gold-light)]"
                  >
                    {salesperson.pin_set ? "Change PIN" : "Set PIN"}
                  </Button>
                </div>
                {expandedSalespersonId === salesperson.id ? (
                  <PinEditorRow
                    key={`pin-editor-${salesperson.id}`}
                    onCancel={() => setExpandedSalespersonId(null)}
                    onSave={(pin) => savePin(salesperson.id, pin)}
                    salespersonName={salesperson.name}
                  />
                ) : null}
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function PinStatusBadge({ pinSet }: { pinSet: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex w-fit items-center gap-2 rounded-full border px-2.5 py-1 text-xs font-medium",
        pinSet
          ? "border-[var(--mk-success)]/30 bg-[var(--mk-success)]/10 text-[var(--mk-text-on-dark)]"
          : "border-[var(--mk-danger)]/30 bg-[var(--mk-danger)]/10 text-[var(--mk-text-on-dark)]",
      )}
    >
      <span
        className={cn(
          "size-2 rounded-full",
          pinSet ? "bg-[var(--mk-success)]" : "bg-[var(--mk-danger)]",
        )}
      />
      {pinSet ? "PIN Set" : "No PIN"}
    </span>
  );
}

function PinEditorRow({
  onCancel,
  onSave,
  salespersonName,
}: {
  onCancel: () => void;
  onSave: (pin: string) => Promise<void>;
  salespersonName: string;
}) {
  const [digits, setDigits] = useState(["", "", "", ""]);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const updateDigit = (index: number, value: string, input: HTMLInputElement) => {
    const nextDigit = value.replace(/\D/g, "").slice(-1);
    setDigits((previous) => previous.map((digit, digitIndex) =>
      digitIndex === index ? nextDigit : digit,
    ));
    setError(null);

    if (nextDigit && input.nextElementSibling instanceof HTMLInputElement) {
      input.nextElementSibling.focus();
    }
  };

  const handleKeyDown = (
    index: number,
    event: React.KeyboardEvent<HTMLInputElement>,
  ) => {
    if (event.key !== "Backspace" || digits[index]) {
      return;
    }

    const previousInput = event.currentTarget.previousElementSibling;
    if (previousInput instanceof HTMLInputElement) {
      previousInput.focus();
    }
  };

  const handleSave = async () => {
    const pin = digits.join("");
    if (!/^\d{4}$/.test(pin)) {
      setError("PIN must be exactly 4 digits");
      return;
    }

    setIsSaving(true);
    setError(null);
    try {
      await onSave(pin);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "PIN update failed");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="border-t border-white/10 bg-black/25 px-4 py-4">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <label className="space-y-2">
          <span className="block text-sm font-medium text-zinc-100">
            New PIN for {salespersonName}
          </span>
          <span className="flex gap-2">
            {digits.map((digit, index) => (
              <input
                key={index}
                aria-label={`PIN digit ${index + 1}`}
                value={digit}
                inputMode="numeric"
                maxLength={1}
                type="tel"
                onChange={(event) => updateDigit(index, event.target.value, event.currentTarget)}
                onKeyDown={(event) => handleKeyDown(index, event)}
                className="size-12 rounded-lg border border-[var(--mk-gold)]/25 bg-[var(--mk-dark)] text-center font-mono text-xl font-semibold text-[var(--mk-gold-light)] outline-none transition focus:border-[var(--mk-gold)] focus:ring-2 focus:ring-[var(--mk-gold)]/20"
              />
            ))}
          </span>
        </label>

        <div className="flex flex-wrap items-center gap-2">
          {error ? (
            <span className="w-full text-sm text-[var(--mk-danger)] lg:w-auto">
              {error}
            </span>
          ) : null}
          <Button
            type="button"
            onClick={() => void handleSave()}
            disabled={isSaving}
            className="min-h-10 bg-[var(--mk-gold)] text-[var(--mk-dark)] hover:bg-[var(--mk-gold-light)]"
          >
            {isSaving ? "Saving" : "Save"}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={onCancel}
            disabled={isSaving}
            className="min-h-10 border-white/10 bg-transparent text-zinc-300 hover:border-white/20 hover:bg-white/[0.04] hover:text-zinc-100"
          >
            Cancel
          </Button>
        </div>
      </div>
    </div>
  );
}

function ConversationView({
  events,
  isLoading,
  lastUpdated,
  onBack,
  onDeleteSession,
  onSaveFeedback,
  onSelectSession,
  savedFeedbackIds,
  salesperson,
  selectedSession,
  stats,
  store,
  storeSessions,
}: {
  events: SessionEvent[];
  isLoading: boolean;
  lastUpdated: Date | null;
  onBack: () => void;
  onDeleteSession: (sessionId: string) => Promise<void>;
  onSaveFeedback: (eventId: number, feedback: FeedbackValue) => Promise<void>;
  onSelectSession: (session: Session) => Promise<void>;
  savedFeedbackIds: Set<number>;
  salesperson: Salesperson;
  selectedSession: Session | null;
  stats: Stats;
  store: Store;
  storeSessions: Session[];
}) {
  const salespersonSessions = storeSessions.filter((session) =>
    sessionBelongsToSalesperson(session, salesperson),
  );
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(null);
  const [deletingSessionId, setDeletingSessionId] = useState<string | null>(null);
  const [deleteMessage, setDeleteMessage] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    if (!deleteMessage) {
      return;
    }

    const timeout = window.setTimeout(() => setDeleteMessage(null), 2000);
    return () => window.clearTimeout(timeout);
  }, [deleteMessage]);

  const confirmDeleteSession = async (sessionId: string) => {
    setDeletingSessionId(sessionId);
    setDeleteError(null);

    try {
      await onDeleteSession(sessionId);
      setConfirmingDeleteId(null);
      setDeleteMessage("Session deleted");
    } catch {
      setDeleteError("Failed to delete. Try again.");
      setConfirmingDeleteId(null);
    } finally {
      setDeletingSessionId(null);
    }
  };

  return (
    <section className="flex min-h-0 flex-col gap-5">
      <ViewHeader
        onBack={onBack}
        subtitle={`${store.name} > ${salesperson.name}`}
        title="Conversation view"
      />

      <div className="grid gap-4 xl:grid-cols-[340px_minmax(0,1fr)]">
        <aside className="space-y-4">
          <Card className="border-white/10 bg-[var(--mk-surface)] shadow-none">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
                <Headphones className="size-4 text-[var(--mk-gold)]" />
                Session Info
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <InfoRow label="Salesperson" value={salesperson.name} />
              <InfoRow label="Store" value={store.name} />
              <InfoRow label="Start Time" value={formatTimestamp(selectedSession?.start_time)} />
              <InfoRow
                label="Duration"
                value={formatDuration(selectedSession?.start_time, selectedSession?.end_time)}
              />
              <InfoRow label="Sessions" value={`${salespersonSessions.length} in this store`} />
            </CardContent>
          </Card>

          <Card className="border-white/10 bg-[var(--mk-surface)] shadow-none">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
                <Clock3 className="size-4 text-[var(--mk-gold)]" />
                Sessions
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {deleteMessage ? (
                <div className="rounded-lg border border-[var(--mk-success)]/25 bg-[var(--mk-success)]/10 p-2.5 text-sm text-zinc-100">
                  {deleteMessage}
                </div>
              ) : null}
              {deleteError ? (
                <div className="rounded-lg border border-[var(--danger)]/25 bg-[var(--danger)]/10 p-2.5 text-sm text-zinc-100">
                  {deleteError}
                </div>
              ) : null}
              {salespersonSessions.length === 0 ? (
                <EmptyState>No sessions found for this salesperson.</EmptyState>
              ) : (
                salespersonSessions.map((session) => (
                  <SessionListRow
                    key={session.session_id}
                    confirmingDelete={confirmingDeleteId === session.session_id}
                    isDeleting={deletingSessionId === session.session_id}
                    isSelected={selectedSession?.session_id === session.session_id}
                    onCancelDelete={() => {
                      setConfirmingDeleteId(null);
                      setDeleteError(null);
                    }}
                    onConfirmDelete={() => void confirmDeleteSession(session.session_id)}
                    onRequestDelete={() => {
                      setConfirmingDeleteId(session.session_id);
                      setDeleteError(null);
                    }}
                    onSelect={() => void onSelectSession(session)}
                    session={session}
                  />
                ))
              )}
            </CardContent>
          </Card>

          <Card className="border-white/10 bg-[var(--mk-surface)] shadow-none">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold text-zinc-100">
                Signal Summary
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {signalRows.map((row) => (
                <div key={row.key} className="flex items-center justify-between gap-3 text-sm">
                  <span className="flex items-center gap-2 text-zinc-400">
                    <span className={cn("size-2 rounded-full", row.tone)} />
                    {row.label}
                  </span>
                  <span className="font-semibold text-zinc-100">{stats[row.key] ?? 0}</span>
                </div>
              ))}
            </CardContent>
          </Card>
        </aside>

        <div className="min-w-0 space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {primaryStatCards.map(({ key, label, icon: Icon }) => (
              <Card key={key} className="border-white/10 bg-[var(--mk-surface)] shadow-none">
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-xs font-medium uppercase tracking-[0.14em] text-zinc-500">
                    {label}
                  </CardTitle>
                  <Icon className="size-4 text-[var(--mk-gold)]" />
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-semibold text-zinc-50">
                    {stats[key] ?? 0}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          <section className="min-h-0 rounded-lg border border-white/10 bg-[var(--mk-surface)]">
            <div className="flex flex-col gap-3 border-b border-white/10 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="font-semibold text-zinc-100">Live Transcript Feed</h2>
                <p className="mt-1 text-sm text-zinc-500">
                  {selectedSession
                    ? `Session #${selectedSession.session_id}`
                    : "No session found for this salesperson yet."}
                </p>
              </div>
              <span className="text-xs text-zinc-500">
                {isLoading ? "Refreshing" : `${events.length} events`}
                {lastUpdated ? `, updated ${lastUpdated.toLocaleTimeString()}` : ""}
              </span>
            </div>

            <div className="max-h-[62vh] space-y-3 overflow-y-auto p-4 lg:max-h-[calc(100vh-330px)]">
              {!selectedSession ? (
                <EmptyState>No transcript session exists for this salesperson yet.</EmptyState>
              ) : events.length === 0 ? (
                <EmptyState>No transcript events for this session yet.</EmptyState>
              ) : (
                events.map((event, index) => (
                  <TranscriptCard
                    key={`${event.id ?? event.timestamp ?? "event"}-${index}`}
                    event={event}
                    onSaveFeedback={onSaveFeedback}
                    savedFeedbackIds={savedFeedbackIds}
                  />
                ))
              )}
            </div>
          </section>
        </div>
      </div>
    </section>
  );
}

function SessionListRow({
  confirmingDelete,
  isDeleting,
  isSelected,
  onCancelDelete,
  onConfirmDelete,
  onRequestDelete,
  onSelect,
  session,
}: {
  confirmingDelete: boolean;
  isDeleting: boolean;
  isSelected: boolean;
  onCancelDelete: () => void;
  onConfirmDelete: () => void;
  onRequestDelete: () => void;
  onSelect: () => void;
  session: Session;
}) {
  if (confirmingDelete) {
    return (
      <div className="rounded-lg border border-white/10 bg-[var(--surface-mid)] p-3">
        <p className="text-sm leading-5 text-zinc-100">
          Delete this session and all its transcripts? This cannot be undone.
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={onConfirmDelete}
            disabled={isDeleting}
            className="min-h-8 rounded-md border border-[var(--danger)] bg-[var(--danger)] px-3 text-xs font-semibold text-white transition hover:bg-[var(--danger)]/85 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isDeleting ? "Deleting" : "Delete"}
          </button>
          <button
            type="button"
            onClick={onCancelDelete}
            disabled={isDeleting}
            className="min-h-8 rounded-md border border-white/10 bg-transparent px-3 text-xs font-medium text-zinc-300 transition hover:border-white/20 hover:bg-white/[0.04] hover:text-zinc-100 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-lg border p-2.5 transition",
        isSelected
          ? "border-[var(--mk-gold)]/45 bg-[var(--mk-gold)]/10"
          : "border-white/10 bg-white/[0.035] hover:border-white/20 hover:bg-white/[0.055]",
      )}
    >
      <button
        type="button"
        onClick={onSelect}
        className="min-w-0 flex-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--mk-gold)]/60"
      >
        <span className="block truncate text-sm font-medium text-zinc-100">
          {formatTimestamp(session.start_time)}
        </span>
        <span className="mt-1 flex flex-wrap items-center gap-2 text-xs text-zinc-500">
          <span>{formatDuration(session.start_time, session.end_time)}</span>
          <span className={cn("size-1.5 rounded-full", isActiveSession(session) ? "bg-[var(--mk-success)]" : "bg-zinc-600")} />
          <span>{isActiveSession(session) ? "Active" : "Closed"}</span>
        </span>
      </button>
      <button
        type="button"
        aria-label={`Delete session ${session.session_id}`}
        onClick={onRequestDelete}
        className="inline-flex size-8 shrink-0 items-center justify-center rounded-md border border-transparent text-zinc-500 transition hover:border-[var(--danger)]/30 hover:bg-[var(--danger)]/10 hover:text-[var(--danger)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--danger)]/50"
      >
        <Trash2 className="size-4" />
      </button>
    </div>
  );
}

function TranscriptCard({
  event,
  onSaveFeedback,
  savedFeedbackIds,
}: {
  event: SessionEvent;
  onSaveFeedback: (eventId: number, feedback: FeedbackValue) => Promise<void>;
  savedFeedbackIds: Set<number>;
}) {
  const priority = normalizePriority(event.alert_priority);
  const saved = Boolean(event.id && (event.manager_feedback || savedFeedbackIds.has(event.id)));

  return (
    <article
      className={cn(
        "relative overflow-hidden rounded-lg border bg-[#121212] p-4",
        priority === "high"
          ? "mk-high-alert border-[var(--mk-gold)]/25"
          : "border-white/10",
      )}
    >
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <time className="text-xs text-zinc-500">{formatTimestamp(event.timestamp)}</time>
        <Badge className={priorityClasses(event.alert_priority)}>
          <span className={cn("mr-1.5 size-1.5 rounded-full", priorityDotClasses(event.alert_priority))} />
          {priority}
        </Badge>
      </div>

      <p className="text-sm leading-6 text-zinc-100">
        {event.transcript || "No transcript text captured."}
      </p>

      <div className="mt-3 flex flex-wrap gap-2">
        {signalBadges(event).map((badge) => (
          <span
            key={badge.label}
            className={cn(
              "inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium",
              badge.className,
            )}
          >
            <span className="mr-1.5 size-1.5 rounded-full bg-current" />
            {badge.label}
          </span>
        ))}
      </div>

      <p className="mt-3 border-l-2 border-[var(--mk-gold)]/70 pl-3 text-sm leading-6 text-zinc-400">
        {event.reasoning || "No reasoning provided."}
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {saved ? (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-300/20 bg-emerald-400/10 px-3 py-1 text-xs font-medium text-emerald-100">
            <CheckCircle2 className="size-3.5" />
            Feedback saved
          </span>
        ) : event.id ? (
          feedbackOptions.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => void onSaveFeedback(event.id as number, option.value)}
              className={cn(
                "min-h-8 rounded-full border px-3 py-1 text-xs font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--mk-gold)]/60",
                option.value === "useful"
                  ? "border-[var(--mk-gold)]/55 text-[var(--mk-gold-light)] hover:bg-[var(--mk-gold)]/10"
                  : "border-white/10 text-zinc-400 hover:border-white/20 hover:bg-white/[0.04] hover:text-zinc-100",
              )}
            >
              {option.label}
            </button>
          ))
        ) : null}
      </div>
    </article>
  );
}

function ViewHeader({
  onBack,
  subtitle,
  title,
}: {
  onBack: () => void;
  subtitle: string;
  title: string;
}) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <p className="truncate text-sm text-[var(--mk-gold)]">{subtitle}</p>
        <h2 className="mt-1 text-2xl font-semibold tracking-tight text-zinc-50 sm:text-3xl">{title}</h2>
      </div>
      <Button
        type="button"
        variant="outline"
        onClick={onBack}
        className="min-h-10 w-fit border-white/10 bg-[var(--mk-surface)] text-zinc-200 hover:border-[var(--mk-gold)]/60 hover:bg-white/[0.04] hover:text-zinc-50"
      >
        <ArrowLeft className="size-4" />
        Back
      </Button>
    </div>
  );
}

function SectionIntro({
  description,
  eyebrow,
  title,
}: {
  description: string;
  eyebrow: string;
  title: string;
}) {
  return (
    <div>
      <p className="text-xs uppercase tracking-[0.18em] text-[var(--mk-gold)]">
        {eyebrow}
      </p>
      <h2 className="mt-2 text-3xl font-semibold tracking-tight text-zinc-50">{title}</h2>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-zinc-400">{description}</p>
    </div>
  );
}

function StatusBadge({ active }: { active: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex w-fit items-center gap-2 rounded-full border px-2.5 py-1 text-xs font-medium",
        active
          ? "border-emerald-300/25 bg-emerald-400/10 text-emerald-100"
          : "border-white/10 bg-white/[0.04] text-zinc-400",
      )}
    >
      <CircleDot className="size-3.5" />
      {active ? "Active" : "Idle"}
    </span>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-white/10 pb-3 last:border-b-0 last:pb-0">
      <span className="text-sm text-zinc-500">{label}</span>
      <span className="text-right text-sm font-medium text-zinc-100">{value}</span>
    </div>
  );
}

function EmptyState({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.035] p-6 text-sm text-zinc-400">
      {children}
    </div>
  );
}
