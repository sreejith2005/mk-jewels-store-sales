"use client";

import {
  AlertTriangle,
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
import {
  Bar,
  BarChart,
  Cell,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { cn } from "@/lib/utils";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:5000";
const REFRESH_MS = 8000;
const GOLD = "#B8860B";

type Session = {
  salesperson_name?: string;
  session_id: string;
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
  { value: "useful", label: "👍 Useful" },
  { value: "false_alarm", label: "👎 False Alarm" },
  { value: "noted", label: "📝 Noted" },
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

function isActiveSession(session: Session) {
  if (typeof session.is_active === "boolean") {
    return session.is_active;
  }

  return !session.end_time;
}

function formatTimestamp(value?: string) {
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

export default function Page() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [events, setEvents] = useState<SessionEvent[]>([]);
  const [savedFeedbackIds, setSavedFeedbackIds] = useState<Set<number>>(() => new Set());
  const [stats, setStats] = useState<Stats>(emptyStats);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const selectedSession = useMemo(
    () => sessions.find((session) => session.session_id === selectedSessionId) ?? null,
    [selectedSessionId, sessions],
  );

  const loadDashboard = useCallback(async () => {
    setError(null);

    try {
      const nextSessions = await fetchJson<Session[]>(`${API_BASE}/api/sessions`);
      setSessions(nextSessions);

      const nextSelectedId =
        nextSessions.find((session) => session.session_id === selectedSessionId)
          ?.session_id ??
        nextSessions[0]?.session_id ??
        null;

      if (nextSelectedId !== selectedSessionId) {
        setSelectedSessionId(nextSelectedId);
      }

      if (!nextSelectedId) {
        setEvents([]);
        setStats(emptyStats);
        setLastUpdated(new Date());
        return;
      }

      const [nextEvents, nextStats] = await Promise.all([
        fetchJson<SessionEvent[]>(
          `${API_BASE}/api/events/${encodeURIComponent(nextSelectedId)}`,
        ),
        fetchJson<Stats>(`${API_BASE}/api/stats/${encodeURIComponent(nextSelectedId)}`),
      ]);

      setEvents(nextEvents);
      setStats({ ...emptyStats, ...nextStats });
      setLastUpdated(new Date());
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Dashboard refresh failed");
    } finally {
      setIsLoading(false);
    }
  }, [selectedSessionId]);

  useEffect(() => {
    const initialRefresh = window.setTimeout(() => void loadDashboard(), 0);
    const interval = window.setInterval(() => void loadDashboard(), REFRESH_MS);

    return () => {
      window.clearTimeout(initialRefresh);
      window.clearInterval(interval);
    };
  }, [loadDashboard]);

  const saveFeedback = useCallback(async (eventId: number, feedback: FeedbackValue) => {
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
  }, []);

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

  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="flex min-h-screen flex-col lg:flex-row">
        <aside className="w-full border-b border-zinc-800/90 bg-zinc-950/95 p-5 lg:h-screen lg:w-[280px] lg:border-r lg:border-b-0">
          <div className="mb-8 border-b border-zinc-800 pb-5">
            <div className="flex items-center gap-3">
              <div className="flex size-10 items-center justify-center rounded-lg border border-[#B8860B]/45 bg-[#B8860B]/10 text-[#B8860B]">
                <Gem className="size-5" />
              </div>
              <div>
                <h1 className="text-xl font-semibold tracking-tight text-zinc-50">
                  MK Jewels
                </h1>
                <p className="text-xs uppercase tracking-[0.22em] text-[#B8860B]">
                  Live Store Floor
                </p>
              </div>
            </div>
          </div>

          <div className="mb-3 flex items-center justify-between text-xs uppercase tracking-[0.18em] text-zinc-500">
            <span>Salespeople</span>
            <span>{sessions.length}</span>
          </div>

          <div className="flex gap-3 overflow-x-auto pb-2 lg:max-h-[calc(100vh-170px)] lg:flex-col lg:overflow-y-auto lg:overflow-x-hidden lg:pr-1">
            {isLoading && sessions.length === 0 ? (
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4 text-sm text-zinc-400">
                Loading active sessions
              </div>
            ) : sessions.length === 0 ? (
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4 text-sm text-zinc-400">
                No active salesperson sessions found.
              </div>
            ) : (
              sessions.map((session) => {
                const active = isActiveSession(session);
                const selected = session.session_id === selectedSessionId;

                return (
                  <button
                    key={session.session_id}
                    type="button"
                    onClick={() => setSelectedSessionId(session.session_id)}
                    className={cn(
                      "min-w-64 rounded-lg border bg-zinc-900/70 p-4 text-left transition hover:border-[#B8860B]/45 hover:bg-zinc-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B8860B]/70 lg:min-w-0",
                      selected
                        ? "border-[#B8860B]/70 shadow-[inset_3px_0_0_#B8860B]"
                        : "border-zinc-800",
                    )}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <h2 className="font-medium text-zinc-50">
                          {session.salesperson_name || "Unknown salesperson"}
                        </h2>
                        <p className="mt-1 text-xs text-zinc-500">
                          {formatTimestamp(session.start_time)}
                        </p>
                      </div>
                      {active ? (
                        <span className="mt-1 flex size-3 rounded-full bg-emerald-400 shadow-[0_0_16px_rgba(52,211,153,0.85)]">
                          <span className="size-3 animate-ping rounded-full bg-emerald-400" />
                        </span>
                      ) : (
                        <span className="mt-1 size-3 rounded-full bg-zinc-600" />
                      )}
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </aside>

        <section className="flex min-w-0 flex-1 flex-col p-4 sm:p-6 lg:h-screen lg:overflow-hidden">
          <header className="mb-5 flex flex-col gap-4 border-b border-zinc-800 pb-5 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <div className="mb-2 flex items-center gap-2 text-sm text-[#B8860B]">
                <Headphones className="size-4" />
                <span>Live transcript monitor</span>
              </div>
              <h2 className="text-3xl font-semibold tracking-tight text-zinc-50">
                {selectedSession?.salesperson_name || "Select a salesperson"}
              </h2>
              <p className="mt-1 text-sm text-zinc-500">
                {selectedSession
                  ? `Session started ${formatTimestamp(selectedSession.start_time)}`
                  : "Choose an active session from the store floor list."}
              </p>
            </div>
            <div className="text-sm text-zinc-500">
              Auto-refresh every 8s
              {lastUpdated ? (
                <span className="block text-zinc-300">
                  Last updated {lastUpdated.toLocaleTimeString()}
                </span>
              ) : null}
            </div>
          </header>

          {error ? (
            <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">
              Could not refresh dashboard: {error}
            </div>
          ) : null}

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-8">
            {statCards.map(({ key, label, icon: Icon }) => (
              <Card key={key} className="border-zinc-800 bg-zinc-900/70">
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

            <Card className="border-zinc-800 bg-zinc-900/70 sm:col-span-2 xl:col-span-4 2xl:col-span-2">
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

          <section className="mt-5 min-h-0 flex-1 rounded-lg border border-zinc-800 bg-zinc-950/80">
            <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
              <h3 className="font-medium text-zinc-100">Transcript Feed</h3>
              <span className="text-xs text-zinc-500">{events.length} events</span>
            </div>

            <div className="max-h-[52vh] space-y-3 overflow-y-auto p-4 lg:max-h-[calc(100vh-390px)]">
              {!selectedSession ? (
                <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-6 text-sm text-zinc-400">
                  Select a salesperson to view live transcript events.
                </div>
              ) : events.length === 0 ? (
                <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-6 text-sm text-zinc-400">
                  No transcript events for this session yet.
                </div>
              ) : (
                events.map((event, index) => (
                  <article
                    key={`${event.id ?? event.timestamp ?? "event"}-${index}`}
                    className="rounded-lg border border-zinc-800 bg-zinc-900/65 p-4"
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
                      {event.id && (event.manager_feedback || savedFeedbackIds.has(event.id)) ? (
                        <span className="text-xs font-medium text-emerald-400">
                          Feedback saved
                        </span>
                      ) : event.id ? (
                        feedbackOptions.map((option) => (
                          <button
                            key={option.value}
                            type="button"
                            onClick={() => void saveFeedback(event.id as number, option.value)}
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
      </div>
    </main>
  );
}
