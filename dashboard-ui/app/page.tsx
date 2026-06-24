"use client";

import {
  AlertTriangle,
  ArrowLeft,
  Gem,
  Headphones,
  MessageSquareText,
  ReceiptText,
  ShieldQuestion,
  Sparkles,
  TrendingUp,
  Users,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Bar, BarChart, Cell, Tooltip, XAxis, YAxis } from "recharts";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:5000";
const REFRESH_MS = 8000;
const GOLD = "#B8860B";

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
  is_active?: number | boolean;
  created_at?: string;
};

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

const statCards: Array<{
  key: keyof Stats;
  label: string;
  icon: LucideIcon;
}> = [
  { key: "total_events", label: "Total Events", icon: MessageSquareText },
  { key: "alerts_fired", label: "Alerts Fired", icon: Zap },
  { key: "objections", label: "Objections", icon: AlertTriangle },
  { key: "price_concerns", label: "Price Concerns", icon: ReceiptText },
  { key: "certification_questions", label: "Cert Questions", icon: ShieldQuestion },
  { key: "upsell_misses", label: "Upsell Misses", icon: Sparkles },
  { key: "high_intent_signals", label: "High Intent", icon: TrendingUp },
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

function normalizePriority(priority?: string) {
  const value = String(priority || "none").toLowerCase();
  return ["high", "medium", "low", "none"].includes(value) ? value : "none";
}

function priorityClasses(priority?: string) {
  switch (normalizePriority(priority)) {
    case "high":
      return "border-red-500/40 bg-red-500/15 text-red-200";
    case "medium":
      return "border-orange-500/40 bg-orange-500/15 text-orange-200";
    case "low":
      return "border-yellow-500/40 bg-yellow-500/15 text-yellow-100";
    default:
      return "border-zinc-600/60 bg-zinc-800 text-zinc-300";
  }
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

export default function Page() {
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
      const nextSelectedSession = newestSessionForSalesperson(
        nextSessions,
        selectedSalesperson,
      );

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
  }, [selectedSalesperson, selectedStore]);

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

  const chartData = useMemo(
    () => [
      { name: "Alerts", value: stats.alerts_fired, fill: "#D97706" },
      { name: "Obj", value: stats.objections, fill: "#EF4444" },
      { name: "Price", value: stats.price_concerns, fill: "#F59E0B" },
      { name: "Cert", value: stats.certification_questions, fill: "#EAB308" },
      { name: "Upsell", value: stats.upsell_misses, fill: GOLD },
      { name: "Intent", value: stats.high_intent_signals, fill: "#22C55E" },
    ],
    [stats],
  );

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

  const selectStore = (store: Store) => {
    setSelectedStore(store);
    setSelectedSalesperson(null);
    setSelectedSession(null);
    setEvents([]);
    setStats(emptyStats);
    setLastUpdated(null);
  };

  const backToStores = () => {
    setSelectedStore(null);
    setSelectedSalesperson(null);
    setSelectedSession(null);
    setSalespersons([]);
    setStoreSessions([]);
    setEvents([]);
    setStats(emptyStats);
    setLastUpdated(null);
    void loadStores();
  };

  const backToSalespersons = () => {
    setSelectedSalesperson(null);
    setSelectedSession(null);
    setEvents([]);
    setStats(emptyStats);
    setLastUpdated(null);
    if (selectedStore) {
      void loadSalespersons(selectedStore);
    }
  };

  return (
    <main className="min-h-screen bg-[#0a0a0a] text-zinc-100">
      <div className="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-4 py-6 sm:px-6 lg:px-8">
        <AppBrand />

        {error ? (
          <div className="mb-5 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">
            Could not refresh dashboard: {error}
          </div>
        ) : null}

        {!selectedStore ? (
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
            onSelectSalesperson={setSelectedSalesperson}
            salespersons={salespersons}
            store={selectedStore}
            summaries={salespersonSummaries}
          />
        ) : (
          <ConversationView
            chartData={chartData}
            events={events}
            isLoading={isLoadingConversation}
            lastUpdated={lastUpdated}
            onBack={backToSalespersons}
            onSaveFeedback={saveFeedback}
            savedFeedbackIds={savedFeedbackIds}
            salesperson={selectedSalesperson}
            selectedSession={selectedSession}
            stats={stats}
            store={selectedStore}
            storeSessions={storeSessions}
          />
        )}
      </div>
    </main>
  );
}

function AppBrand() {
  return (
    <header className="mb-6 flex items-center gap-3 border-b border-[#222] pb-5">
      <div className="flex size-10 items-center justify-center rounded-lg border border-[#B8860B]/45 bg-[#B8860B]/10 text-[#B8860B]">
        <Gem className="size-5" />
      </div>
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-zinc-50">MK Jewels</h1>
        <p className="text-xs uppercase tracking-[0.22em] text-[#B8860B]">
          Live Store Floor
        </p>
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
    <section className="flex flex-1 flex-col">
      <div className="mb-5">
        <p className="mb-2 text-sm text-[#B8860B]">Level 1</p>
        <h2 className="text-3xl font-semibold tracking-tight text-zinc-50">
          Select a store
        </h2>
      </div>

      {isLoading && stores.length === 0 ? (
        <EmptyState>Loading stores</EmptyState>
      ) : stores.length === 0 ? (
        <EmptyState>No stores found.</EmptyState>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {stores.map((store) => {
            const activeCount = activeCounts.get(store.id) ?? 0;

            return (
              <button
                key={store.id}
                type="button"
                onClick={() => onSelectStore(store)}
                className="group min-h-44 rounded-lg border border-[#222] bg-[#111] p-5 text-left transition hover:border-[#B8860B]/70 hover:bg-[#151515] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B8860B]/70"
              >
                <div className="flex h-full flex-col justify-between gap-6">
                  <div>
                    <p className="mb-2 text-xs uppercase tracking-[0.18em] text-zinc-500">
                      Store
                    </p>
                    <h3 className="text-2xl font-semibold text-zinc-50">
                      {store.name}
                    </h3>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <Badge className="border-[#B8860B]/40 bg-[#B8860B]/10 text-[#B8860B]">
                      {activeCount} active today
                    </Badge>
                    <span className="text-sm text-zinc-500 transition group-hover:text-zinc-300">
                      Open
                    </span>
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
  return (
    <section className="flex flex-1 flex-col">
      <ViewHeader onBack={onBack} subtitle="Level 2" title={store.name} />

      {isLoading && salespersons.length === 0 ? (
        <EmptyState>Loading salespeople</EmptyState>
      ) : salespersons.length === 0 ? (
        <EmptyState>No salespeople found for this store.</EmptyState>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {salespersons.map((salesperson) => {
            const summary = summaries[salesperson.id] ?? {
              activeSessionCount: 0,
              lastAlertTime: null,
              sessionCountToday: 0,
            };

            return (
              <button
                key={salesperson.id}
                type="button"
                onClick={() => onSelectSalesperson(salesperson)}
                className="group rounded-lg border border-[#222] bg-[#111] p-5 text-left transition hover:border-[#B8860B]/70 hover:bg-[#151515] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B8860B]/70"
              >
                <div className="mb-5 flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <h3 className="truncate text-xl font-semibold text-zinc-50">
                      {salesperson.name}
                    </h3>
                    <p className="mt-1 text-sm text-zinc-500">
                      {salesperson.designation}
                    </p>
                  </div>
                  <span
                    className={cn(
                      "mt-2 size-2.5 rounded-full",
                      summary.activeSessionCount > 0
                        ? "bg-emerald-400 shadow-[0_0_14px_rgba(52,211,153,0.65)]"
                        : "bg-zinc-600",
                    )}
                  />
                </div>

                <div className="grid gap-3 text-sm text-zinc-400">
                  <div className="flex items-center justify-between gap-3">
                    <span>Sessions today</span>
                    <span className="font-medium text-zinc-100">
                      {summary.sessionCountToday}
                    </span>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <span>Last alert</span>
                    <span className="text-right font-medium text-zinc-100">
                      {summary.lastAlertTime
                        ? formatTimestamp(summary.lastAlertTime)
                        : "None today"}
                    </span>
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

function ConversationView({
  chartData,
  events,
  isLoading,
  lastUpdated,
  onBack,
  onSaveFeedback,
  savedFeedbackIds,
  salesperson,
  selectedSession,
  stats,
  store,
  storeSessions,
}: {
  chartData: Array<{ name: string; value: number; fill: string }>;
  events: SessionEvent[];
  isLoading: boolean;
  lastUpdated: Date | null;
  onBack: () => void;
  onSaveFeedback: (eventId: number, feedback: FeedbackValue) => Promise<void>;
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

  return (
    <section className="flex min-h-0 flex-1 flex-col">
      <ViewHeader
        onBack={onBack}
        subtitle={`${salesperson.name} - ${store.name}`}
        title="Conversation view"
      />

      <header className="mb-5 flex flex-col gap-4 border-b border-[#222] pb-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="mb-2 flex items-center gap-2 text-sm text-[#B8860B]">
            <Headphones className="size-4" />
            <span>Live transcript monitor</span>
          </div>
          <h2 className="text-3xl font-semibold tracking-tight text-zinc-50">
            {salesperson.name}
          </h2>
          <p className="mt-1 text-sm text-zinc-500">
            {selectedSession
              ? `Session started ${formatTimestamp(selectedSession.start_time)}`
              : "No session found for this salesperson yet."}
          </p>
        </div>
        <div className="text-sm text-zinc-500">
          Auto-refresh every 8s
          {lastUpdated ? (
            <span className="block text-zinc-300">
              Last updated {lastUpdated.toLocaleTimeString()}
            </span>
          ) : null}
          <span className="block text-zinc-500">
            {salespersonSessions.length} sessions in this store
          </span>
        </div>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-8">
        {statCards.map(({ key, label, icon: Icon }) => (
          <Card key={key} className="border-[#222] bg-[#111]">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-xs font-medium uppercase tracking-[0.14em] text-zinc-500">
                {label}
              </CardTitle>
              <Icon className="size-4 text-[#B8860B]" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-semibold text-zinc-50">
                {stats[key] ?? 0}
              </div>
            </CardContent>
          </Card>
        ))}

        <Card className="border-[#222] bg-[#111] sm:col-span-2 xl:col-span-4 2xl:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-xs font-medium uppercase tracking-[0.14em] text-zinc-500">
              <Users className="size-4 text-[#B8860B]" />
              Signals
            </CardTitle>
          </CardHeader>
          <CardContent className="h-24 overflow-hidden">
            <BarChart
              width={300}
              height={96}
              data={chartData}
              margin={{ top: 4, right: 8, bottom: 0, left: -30 }}
            >
              <XAxis
                dataKey="name"
                tick={{ fill: "#a1a1aa", fontSize: 10 }}
                tickLine={false}
                axisLine={false}
              />
              <YAxis hide allowDecimals={false} />
              <Tooltip
                cursor={{ fill: "rgba(184,134,11,0.08)" }}
                contentStyle={{
                  background: "#18181b",
                  border: "1px solid #3f3f46",
                  borderRadius: 8,
                  color: "#fafafa",
                }}
              />
              <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                {chartData.map((entry) => (
                  <Cell key={entry.name} fill={entry.fill} />
                ))}
              </Bar>
            </BarChart>
          </CardContent>
        </Card>
      </div>

      <section className="mt-5 min-h-0 flex-1 rounded-lg border border-[#222] bg-[#0a0a0a]">
        <div className="flex items-center justify-between border-b border-[#222] px-4 py-3">
          <h3 className="font-medium text-zinc-100">Transcript Feed</h3>
          <span className="text-xs text-zinc-500">
            {isLoading ? "Refreshing" : `${events.length} events`}
          </span>
        </div>

        <div className="max-h-[52vh] space-y-3 overflow-y-auto p-4 lg:max-h-[calc(100vh-430px)]">
          {!selectedSession ? (
            <EmptyState>No transcript session exists for this salesperson yet.</EmptyState>
          ) : events.length === 0 ? (
            <EmptyState>No transcript events for this session yet.</EmptyState>
          ) : (
            events.map((event, index) => (
              <article
                key={`${event.id ?? event.timestamp ?? "event"}-${index}`}
                className="rounded-lg border border-[#222] bg-[#111] p-4"
              >
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <time className="text-xs text-zinc-500">
                    {formatTimestamp(event.timestamp)}
                  </time>
                  <Badge className={priorityClasses(event.alert_priority)}>
                    {normalizePriority(event.alert_priority)}
                  </Badge>
                </div>
                <p className="text-sm leading-6 text-zinc-100">
                  {event.transcript || "No transcript text captured."}
                </p>
                <p className="mt-3 border-l-2 border-[#B8860B]/70 pl-3 text-sm text-zinc-400">
                  {event.reasoning || "No reasoning provided."}
                </p>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  {event.id &&
                  (event.manager_feedback || savedFeedbackIds.has(event.id)) ? (
                    <span className="text-xs font-medium text-emerald-400">
                      Feedback saved
                    </span>
                  ) : event.id ? (
                    feedbackOptions.map((option) => (
                      <button
                        key={option.value}
                        type="button"
                        onClick={() => void onSaveFeedback(event.id as number, option.value)}
                        className="rounded-md border border-zinc-700 bg-zinc-900 px-2.5 py-1 text-xs text-zinc-300 transition hover:border-emerald-500/50 hover:text-zinc-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/70"
                      >
                        {option.label}
                      </button>
                    ))
                  ) : null}
                </div>
              </article>
            ))
          )}
        </div>
      </section>
    </section>
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
    <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <p className="mb-1 text-sm text-[#B8860B]">{subtitle}</p>
        <h2 className="text-3xl font-semibold tracking-tight text-zinc-50">{title}</h2>
      </div>
      <Button
        type="button"
        variant="outline"
        onClick={onBack}
        className="w-fit border-[#222] bg-[#111] text-zinc-200 hover:border-[#B8860B]/70 hover:bg-[#151515] hover:text-zinc-50"
      >
        <ArrowLeft className="size-4" />
        Back
      </Button>
    </div>
  );
}

function EmptyState({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-[#222] bg-[#111] p-6 text-sm text-zinc-400">
      {children}
    </div>
  );
}
