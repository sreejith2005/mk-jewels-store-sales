"use client";

import Image from "next/image";
import {
  AlertTriangle,
  ArrowLeft,
  Award,
  Bell,
  Building2,
  CheckCircle2,
  CircleDot,
  Clock3,
  Headphones,
  KeyRound,
  LayoutDashboard,
  MessageSquareText,
  Minus,
  ReceiptText,
  Search,
  Store as StoreIcon,
  Trash2,
  TrendingDown,
  TrendingUp,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "";
const DASHBOARD_AUTH_USER = process.env.NEXT_PUBLIC_DASHBOARD_AUTH_USER;
const DASHBOARD_AUTH_PASS = process.env.NEXT_PUBLIC_DASHBOARD_AUTH_PASS;
const REFRESH_MS = 2000;

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

type DashboardView = "stores" | "pin-management" | "reports" | "alerts" | "scores";
type ConversationMode = "live" | "full";

type Session = {
  salesperson_name?: string;
  session_id: string;
  store_id?: number | null;
  salesperson_id?: number | null;
  start_time?: string;
  end_time?: string | null;
  is_active?: boolean;
  event_count?: number;
};

type SessionEvent = {
  id?: number;
  timestamp?: string;
  transcript?: string;
  alert_priority?: string;
  reasoning?: string;
  manager_feedback?: FeedbackValue | null;
};

type AlertLogEntry = {
  id?: number;
  timestamp?: string;
  sent_at?: string;
  store_name?: string;
  store?: string;
  salesperson_name?: string;
  salesperson?: string;
  priority?: string;
  alert_priority?: string;
  channel?: string;
  status?: string;
};

type CoachingReport = {
  id?: number;
  report_date?: string;
  date?: string;
  salesperson_name?: string;
  report_text?: string;
  text?: string;
  content?: string;
  created_at?: string;
};

type SessionScore = {
  id?: number;
  session_id: string;
  salesperson_name: string;
  store_name: string;
  greeting_score: number;
  product_knowledge_score: number;
  objection_handling_score: number;
  missed_oppurtuinity: number;
  upsell_score: number;
  closing_score: number;
  overall_score: number;
  score_reasoning?: string;
  customer_satisfaction?: "Positive" | "Neutral" | "Negative" | string;
  created_at?: string;
};

type LeaderboardRow = {
  name: string;
  avg_overall: number;
  session_count: number;
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

const scoreDimensions: Array<{
  key: keyof Pick<
    SessionScore,
    | "greeting_score"
    | "product_knowledge_score"
    | "objection_handling_score"
    | "missed_oppurtuinity"
    | "upsell_score"
    | "closing_score"
  >;
  label: string;
}> = [
  { key: "greeting_score", label: "Greeting & Opening" },
  { key: "product_knowledge_score", label: "Product Knowledge" },
  { key: "objection_handling_score", label: "Objection Handling" },
  { key: "missed_oppurtuinity", label: "Missed Oppurtuinity" },
  { key: "upsell_score", label: "Upsell Attempts / Cross-Selling" },
  { key: "closing_score", label: "Closing Ability" },
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

function fetchAlertsLog() {
  return fetchJson<AlertLogEntry[]>(`${API_BASE}/api/alerts/log?limit=50`);
}

function fetchReports(salespersonName: string) {
  return fetchJson<CoachingReport[]>(
    `${API_BASE}/api/reports/${encodeURIComponent(salespersonName)}`,
  );
}

function fetchSessionScore(sessionId: string) {
  return fetchJson<SessionScore>(
    `${API_BASE}/api/scores/session/${encodeURIComponent(sessionId)}`,
  );
}

function fetchSalespersonScores(salespersonName: string, days = 30) {
  return fetchJson<SessionScore[]>(
    `${API_BASE}/api/scores/salesperson/${encodeURIComponent(salespersonName)}?days=${encodeURIComponent(days)}`,
  );
}

function fetchStoreLeaderboard(storeId: number) {
  return fetchJson<LeaderboardRow[]>(
    `${API_BASE}/api/scores/leaderboard/${encodeURIComponent(storeId)}`,
  );
}

async function generateSessionScore(sessionId: string) {
  const response = await fetch(
    `${API_BASE}/api/scores/generate/${encodeURIComponent(sessionId)}`,
    {
      method: "POST",
      credentials: "include",
      headers: {
        Accept: "application/json",
        ...basicAuthHeader(),
      },
    },
  );

  const payload = await response.json().catch(() => null) as SessionScore | { error?: string } | null;
  if (!response.ok) {
    throw new Error((payload as { error?: string } | null)?.error ?? `${response.status} ${response.statusText}`);
  }

  return payload as SessionScore;
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

function eventStableId(event: SessionEvent, index: number) {
  return String(event.id ?? `${event.timestamp ?? "no-time"}-${event.transcript ?? ""}-${index}`);
}

function sortEventsChronologically(events: SessionEvent[]) {
  return [...events].sort((first, second) => {
    const firstTime = first.timestamp ? new Date(first.timestamp).getTime() : 0;
    const secondTime = second.timestamp ? new Date(second.timestamp).getTime() : 0;
    const timeCompare = (Number.isNaN(firstTime) ? 0 : firstTime) - (Number.isNaN(secondTime) ? 0 : secondTime);
    if (timeCompare !== 0) {
      return timeCompare;
    }

    return (first.id ?? 0) - (second.id ?? 0);
  });
}

function mergeEventsById(previous: SessionEvent[], incoming: SessionEvent[]) {
  const renderedIds = new Set(previous.map(eventStableId));
  const additions = sortEventsChronologically(incoming).filter(
    (event, index) => !renderedIds.has(eventStableId(event, index)),
  );

  return additions.length > 0 ? [...previous, ...additions] : previous;
}

function sortSessionsNewestFirst(sessions: Session[]) {
  return [...sessions].sort((first, second) => {
    const firstTime = first.start_time ? new Date(first.start_time).getTime() : 0;
    const secondTime = second.start_time ? new Date(second.start_time).getTime() : 0;
    return (Number.isNaN(secondTime) ? 0 : secondTime) - (Number.isNaN(firstTime) ? 0 : firstTime);
  });
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
  const [sessionScore, setSessionScore] = useState<SessionScore | null>(null);
  const [, setIsLoadingSessionScore] = useState(false);
  const [isGeneratingSessionScore, setIsGeneratingSessionScore] = useState(false);
  const [savedFeedbackIds, setSavedFeedbackIds] = useState<Set<number>>(
    () => new Set(),
  );
  const [stats, setStats] = useState<Stats>(emptyStats);
  const [isLoadingStores, setIsLoadingStores] = useState(true);
  const [isLoadingSalespersons, setIsLoadingSalespersons] = useState(false);
  const [, setIsLoadingConversation] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [, setLastUpdated] = useState<Date | null>(null);
  const renderedEventIdsRef = useRef<Set<string>>(new Set());

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

  const refreshStoreSessions = useCallback(async (store: Store) => {
    if (salespersons.length === 0) {
      return;
    }

    try {
      const nextSessions = await fetchSessions(store.id);
      const lastAlertTimes = await loadLastAlertTimes(nextSessions, salespersons);

      setStoreSessions(nextSessions);
      setAllSessions((previous) => {
        const otherStoreSessions = previous.filter((session) => session.store_id !== store.id);
        return [...otherStoreSessions, ...nextSessions];
      });
      setSalespersonSummaries(
        Object.fromEntries(
          salespersons.map((salesperson) => [
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
        loadError instanceof Error ? loadError.message : "Session refresh failed",
      );
    }
  }, [salespersons]);

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
        renderedEventIdsRef.current = new Set();
        setEvents([]);
        setStats(emptyStats);
        setSessionScore(null);
        setLastUpdated(new Date());
        return;
      }

      const [nextEvents, nextStats] = await Promise.all([
        fetchEvents(nextSelectedSession.session_id),
        fetchStats(nextSelectedSession.session_id),
      ]);

      setEvents((previous) => {
        const mergedEvents = mergeEventsById(previous, nextEvents);
        renderedEventIdsRef.current = new Set(mergedEvents.map(eventStableId));
        return mergedEvents;
      });
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

  const loadSelectedSessionScore = useCallback(async () => {
    if (!selectedSession) {
      setSessionScore(null);
      return;
    }

    setIsLoadingSessionScore(true);
    try {
      const score = await fetchSessionScore(selectedSession.session_id);
      setSessionScore(score);
    } catch {
      setSessionScore(null);
    } finally {
      setIsLoadingSessionScore(false);
    }
  }, [selectedSession]);

  const generateSelectedSessionScore = useCallback(async () => {
    if (!selectedSession) {
      return;
    }

    setIsGeneratingSessionScore(true);
    setError(null);
    try {
      const score = await generateSessionScore(selectedSession.session_id);
      setSessionScore(score);
    } catch (generateError) {
      setError(
        generateError instanceof Error ? generateError.message : "Score generation failed",
      );
    } finally {
      setIsGeneratingSessionScore(false);
    }
  }, [selectedSession]);

  useEffect(() => {
    const initialRefresh = window.setTimeout(() => void loadStores(), 0);

    return () => {
      window.clearTimeout(initialRefresh);
    };
  }, [loadStores]);

  useEffect(() => {
    const timeout = window.setTimeout(() => void loadSelectedSessionScore(), 0);
    return () => window.clearTimeout(timeout);
  }, [loadSelectedSessionScore]);

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
    if (!selectedStore || salespersons.length === 0) {
      return;
    }

    const interval = window.setInterval(() => void refreshStoreSessions(selectedStore), REFRESH_MS);
    return () => window.clearInterval(interval);
  }, [refreshStoreSessions, salespersons.length, selectedStore]);

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

      const sortedEvents = sortEventsChronologically(nextEvents);
      renderedEventIdsRef.current = new Set(sortedEvents.map(eventStableId));
      setEvents(sortedEvents);
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
        renderedEventIdsRef.current = new Set();
        setEvents([]);
        setStats(emptyStats);
        setSessionScore(null);
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
    renderedEventIdsRef.current = new Set();
    setEvents([]);
    setStats(emptyStats);
    setSessionScore(null);
    setLastUpdated(null);
  };

  const selectSalesperson = (salesperson: Salesperson) => {
    setSelectedSalesperson(salesperson);
    setSelectedSession(null);
    setSessionSelectionPaused(false);
    renderedEventIdsRef.current = new Set();
    setEvents([]);
    setStats(emptyStats);
    setSessionScore(null);
    setLastUpdated(null);
  };

  const backToStores = () => {
    setView("stores");
    setSelectedStore(null);
    setSelectedSalesperson(null);
    setSelectedSession(null);
    setSessionSelectionPaused(false);
    renderedEventIdsRef.current = new Set();
    setSalespersons([]);
    setStoreSessions([]);
    setEvents([]);
    setStats(emptyStats);
    setSessionScore(null);
    setLastUpdated(null);
    void loadStores();
  };

  const openPinManagement = () => {
    setView("pin-management");
    setError(null);
  };

  const openReports = () => {
    setView("reports");
    setSelectedStore(null);
    setSelectedSalesperson(null);
    setSelectedSession(null);
    setSessionSelectionPaused(false);
    renderedEventIdsRef.current = new Set();
    setEvents([]);
    setStats(emptyStats);
    setSessionScore(null);
    setLastUpdated(null);
    setError(null);
  };

  const openAlerts = () => {
    setView("alerts");
    setSelectedStore(null);
    setSelectedSalesperson(null);
    setSelectedSession(null);
    setSessionSelectionPaused(false);
    renderedEventIdsRef.current = new Set();
    setEvents([]);
    setStats(emptyStats);
    setSessionScore(null);
    setLastUpdated(null);
    setError(null);
  };

  const openScores = () => {
    setView("scores");
    setSelectedStore(null);
    setSelectedSalesperson(null);
    setSelectedSession(null);
    setSessionSelectionPaused(false);
    renderedEventIdsRef.current = new Set();
    setEvents([]);
    setStats(emptyStats);
    setSessionScore(null);
    setLastUpdated(null);
    setError(null);
  };

  const backToSalespersons = () => {
    setSelectedSalesperson(null);
    setSelectedSession(null);
    setSessionSelectionPaused(false);
    renderedEventIdsRef.current = new Set();
    setEvents([]);
    setStats(emptyStats);
    setSessionScore(null);
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
          onSelectAlerts={openAlerts}
          onSelectPinManagement={openPinManagement}
          onSelectReports={openReports}
          onSelectScores={openScores}
          onSelectStores={backToStores}
          selectedSalesperson={selectedSalesperson}
          selectedStore={selectedStore}
        />

        <div className="min-w-0 flex-1">
          <DashboardTopbar
            activeSessions={activeSessions}
            activeView={view}
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
            ) : view === "reports" ? (
              <ReportsView stores={stores} />
            ) : view === "alerts" ? (
              <AlertsView />
            ) : view === "scores" ? (
              <ScoresView stores={stores} />
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
                onBack={backToSalespersons}
                onDeleteSession={removeDeletedSession}
                onSaveFeedback={saveFeedback}
                onSelectSession={selectSession}
                savedFeedbackIds={savedFeedbackIds}
                salesperson={selectedSalesperson}
                sessionScore={sessionScore}
                selectedSession={selectedSession}
                isGeneratingSessionScore={isGeneratingSessionScore}
                onGenerateSessionScore={generateSelectedSessionScore}
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
  onSelectAlerts,
  onSelectPinManagement,
  onSelectReports,
  onSelectScores,
  onSelectStores,
  selectedSalesperson,
  selectedStore,
}: {
  activeSessions: number;
  activeView: DashboardView;
  onSelectAlerts: () => void;
  onSelectPinManagement: () => void;
  onSelectReports: () => void;
  onSelectScores: () => void;
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
    { label: "Scores", icon: Award, active: activeView === "scores", action: onSelectScores },
    { label: "Reports", icon: LayoutDashboard, active: activeView === "reports", action: onSelectReports },
    { label: "Alerts Log", icon: Bell, active: activeView === "alerts", action: onSelectAlerts },
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
              : activeView === "scores"
                ? "Sales Scores"
              : activeView === "reports"
                ? "Coaching Reports"
                : activeView === "alerts"
                  ? "Alerts Log"
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
  selectedSalesperson,
  selectedSession,
  selectedStore,
}: {
  activeSessions: number;
  activeView: DashboardView;
  selectedSalesperson: Salesperson | null;
  selectedSession: Session | null;
  selectedStore: Store | null;
}) {
  const istTime = useIstTime();
  const breadcrumb = activeView === "pin-management"
    ? ["PIN Management"]
    : activeView === "scores"
      ? ["Scores"]
    : activeView === "reports"
      ? ["Reports"]
      : activeView === "alerts"
        ? ["Alerts Log"]
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
              : activeView === "scores"
                ? "Scores"
              : activeView === "reports"
                ? "Coaching Reports"
                : activeView === "alerts"
                  ? "Alerts Log"
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

function AlertsView() {
  const [alerts, setAlerts] = useState<AlertLogEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const loadAlerts = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);

    try {
      setAlerts(await fetchAlertsLog());
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Alerts refresh failed");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    const initialRefresh = window.setTimeout(() => void loadAlerts(), 0);
    const interval = window.setInterval(() => void loadAlerts(), REFRESH_MS);
    return () => {
      window.clearTimeout(initialRefresh);
      window.clearInterval(interval);
    };
  }, [loadAlerts]);

  return (
    <section className="flex flex-col gap-5">
      <SectionIntro
        eyebrow="Alerts"
        title="Alerts log"
        description="Review the most recent manager notifications sent from live conversations."
      />

      {loadError ? (
        <div className="rounded-lg border border-[var(--mk-danger)]/30 bg-[var(--mk-danger)]/10 p-3 text-sm text-zinc-100">
          Could not refresh alerts: {loadError}
        </div>
      ) : null}

      <div className="overflow-hidden rounded-lg border border-white/10 bg-[var(--mk-surface)]">
        <div className="hidden grid-cols-[1.2fr_1fr_1fr_0.8fr_0.8fr_0.8fr] gap-4 border-b border-white/10 px-4 py-3 text-xs uppercase tracking-[0.14em] text-zinc-500 lg:grid">
          <span>Time</span>
          <span>Store</span>
          <span>Salesperson</span>
          <span>Priority</span>
          <span>Channel</span>
          <span>Status</span>
        </div>
        <div className="divide-y divide-white/10">
          {isLoading && alerts.length === 0 ? (
            <div className="p-4">
              <EmptyState>Loading alerts</EmptyState>
            </div>
          ) : alerts.length === 0 ? (
            <div className="p-4">
              <EmptyState>No alerts logged yet</EmptyState>
            </div>
          ) : (
            alerts.map((alert, index) => {
              const alertTime = alert.sent_at ?? alert.timestamp;
              const priority = normalizePriority(alert.priority ?? alert.alert_priority);
              const status = alert.status ?? "sent";

              return (
                <div
                  key={alert.id ?? `${alertTime ?? "alert"}-${index}`}
                  className="grid gap-3 px-4 py-4 text-sm lg:grid-cols-[1.2fr_1fr_1fr_0.8fr_0.8fr_0.8fr] lg:items-center"
                >
                  <time className="text-zinc-400">{formatTimestamp(alertTime)}</time>
                  <span className="text-zinc-200">{alert.store_name ?? alert.store ?? "Unknown store"}</span>
                  <span className="text-zinc-200">{alert.salesperson_name ?? alert.salesperson ?? "Unknown"}</span>
                  <span className="inline-flex w-fit items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-xs font-medium uppercase text-zinc-100">
                    <span className={cn("size-2 rounded-full", priorityDotClasses(priority))} />
                    {priority === "none" ? "unknown" : priority}
                  </span>
                  <span className="text-zinc-400">{alert.channel ?? "default"}</span>
                  <span className={cn(
                    "w-fit rounded-full border px-2.5 py-1 text-xs font-medium",
                    status === "failed"
                      ? "border-red-400/25 bg-red-500/10 text-red-100"
                      : status === "skipped"
                        ? "border-zinc-500/25 bg-white/[0.04] text-zinc-300"
                        : "border-emerald-300/20 bg-emerald-400/10 text-emerald-100",
                  )}>
                    {status}
                  </span>
                </div>
              );
            })
          )}
        </div>
      </div>
    </section>
  );
}

function ReportsView({ stores }: { stores: Store[] }) {
  const [allSalespersons, setAllSalespersons] = useState<Salesperson[]>([]);
  const [selectedName, setSelectedName] = useState("");
  const [reports, setReports] = useState<CoachingReport[]>([]);
  const [isLoadingSalespersons, setIsLoadingSalespersons] = useState(false);
  const [isLoadingReports, setIsLoadingReports] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (stores.length === 0) {
      setAllSalespersons([]);
      return;
    }

    let cancelled = false;
    setIsLoadingSalespersons(true);
    setLoadError(null);

    Promise.all(stores.map((store) => fetchStoreSalespersons(store.id)))
      .then((salespersonGroups) => {
        if (!cancelled) {
          setAllSalespersons(salespersonGroups.flat());
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setLoadError(error instanceof Error ? error.message : "Salesperson list refresh failed");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoadingSalespersons(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [stores]);

  useEffect(() => {
    if (!selectedName) {
      setReports([]);
      return;
    }

    let cancelled = false;
    setIsLoadingReports(true);
    setLoadError(null);

    fetchReports(selectedName)
      .then((nextReports) => {
        if (!cancelled) {
          setReports([...nextReports].sort((first, second) => {
            const firstDate = first.report_date ?? first.date ?? first.created_at ?? "";
            const secondDate = second.report_date ?? second.date ?? second.created_at ?? "";
            return firstDate.localeCompare(secondDate);
          }));
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setLoadError(error instanceof Error ? error.message : "Reports refresh failed");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoadingReports(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [selectedName]);

  return (
    <section className="flex flex-col gap-5">
      <div className="flex flex-col gap-4 rounded-lg border border-white/10 bg-[var(--mk-surface)] p-5 md:flex-row md:items-end md:justify-between">
        <SectionIntro
          eyebrow="Reports"
          title="Coaching reports"
          description="Read the latest seven days of nightly salesperson coaching notes."
        />

        <label className="w-full md:max-w-sm">
          <span className="text-xs uppercase tracking-[0.14em] text-zinc-500">
            Salesperson
          </span>
          <select
            value={selectedName}
            onChange={(event) => setSelectedName(event.target.value)}
            className="mt-2 h-11 w-full rounded-lg border border-white/10 bg-black/35 px-3 text-sm text-zinc-100 outline-none transition focus:border-[var(--mk-gold)]/60 focus:ring-2 focus:ring-[var(--mk-gold)]/15"
          >
            <option value="">
              {isLoadingSalespersons ? "Loading salespeople" : "Select salesperson"}
            </option>
            {allSalespersons.map((salesperson) => (
              <option key={salesperson.id} value={salesperson.name}>
                {salesperson.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {loadError ? (
        <div className="rounded-lg border border-[var(--mk-danger)]/30 bg-[var(--mk-danger)]/10 p-3 text-sm text-zinc-100">
          Could not refresh reports: {loadError}
        </div>
      ) : null}

      {!selectedName ? (
        <EmptyState>Select a salesperson to view recent coaching reports.</EmptyState>
      ) : isLoadingReports && reports.length === 0 ? (
        <EmptyState>Loading reports</EmptyState>
      ) : reports.length === 0 ? (
        <EmptyState>No reports generated yet. Reports are generated nightly at 9pm.</EmptyState>
      ) : (
        <div className="grid gap-3">
          {reports.map((report, index) => {
            const reportDate = report.report_date ?? report.date ?? report.created_at ?? "";
            const reportText = report.report_text ?? report.text ?? report.content ?? "";

            return (
              <article
                key={report.id ?? `${reportDate}-${index}`}
                className="rounded-lg border border-white/10 bg-[var(--mk-surface)] p-4"
              >
                <h3 className="text-sm font-semibold text-[var(--mk-gold-light)]">
                  {formatTimestamp(reportDate)}
                </h3>
                <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-zinc-200">
                  {reportText || "No report text captured."}
                </p>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

function ScoresView({ stores }: { stores: Store[] }) {
  const [selectedStoreId, setSelectedStoreId] = useState<number | "">(
    stores[0]?.id ?? "",
  );
  const [leaderboard, setLeaderboard] = useState<LeaderboardRow[]>([]);
  const [expandedName, setExpandedName] = useState<string | null>(null);
  const [salespersonScores, setSalespersonScores] = useState<Record<string, SessionScore[]>>({});
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const effectiveStoreId = selectedStoreId || stores[0]?.id || "";

  useEffect(() => {
    if (!effectiveStoreId) {
      return;
    }

    let cancelled = false;
    setIsLoading(true);
    setError(null);
    fetchStoreLeaderboard(Number(effectiveStoreId))
      .then((rows) => {
        if (!cancelled) {
          setLeaderboard(rows);
        }
      })
      .catch((loadError) => {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "Scores failed to load");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [effectiveStoreId]);

  const toggleSalesperson = async (name: string) => {
    if (expandedName === name) {
      setExpandedName(null);
      return;
    }

    setExpandedName(name);
    if (salespersonScores[name]) {
      return;
    }

    try {
      const scores = await fetchSalespersonScores(name, 90);
      setSalespersonScores((previous) => ({ ...previous, [name]: scores }));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Salesperson scores failed to load");
    }
  };

  return (
    <section className="flex flex-col gap-5">
      <SectionIntro
        eyebrow="Scores"
        title="Salesperson scoring"
        description="Compare completed sessions by AI-scored sales behavior and review recent score history."
      />

      <Card className="border-white/10 bg-[var(--mk-surface)] shadow-none">
        <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
          <label className="text-sm text-zinc-400" htmlFor="score-store">
            Store
          </label>
          <select
            id="score-store"
            value={effectiveStoreId}
            onChange={(event) => {
              setSelectedStoreId(event.target.value ? Number(event.target.value) : "");
              setExpandedName(null);
            }}
            className="min-h-10 rounded-md border border-white/10 bg-black/30 px-3 text-sm text-zinc-100 outline-none transition focus:border-[var(--mk-gold)]/60"
          >
            {stores.length === 0 ? <option value="">No stores found</option> : null}
            {stores.map((store) => (
              <option key={store.id} value={store.id}>
                {store.name}
              </option>
            ))}
          </select>
        </CardContent>
      </Card>

      {error ? (
        <div className="rounded-lg border border-red-400/25 bg-red-500/10 p-3 text-sm text-red-100">
          {error}
        </div>
      ) : null}

      <Card className="border-white/10 bg-[var(--mk-surface)] shadow-none">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
            <Award className="size-4 text-[var(--mk-gold)]" />
            Leaderboard
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <EmptyState>Loading scores...</EmptyState>
          ) : leaderboard.length === 0 ? (
            <EmptyState>No scored sessions found for this store yet.</EmptyState>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead className="border-b border-white/10 text-xs uppercase tracking-[0.14em] text-zinc-500">
                  <tr>
                    <th className="py-3 pr-4 font-medium">Rank</th>
                    <th className="py-3 pr-4 font-medium">Name</th>
                    <th className="py-3 pr-4 font-medium">Avg Score</th>
                    <th className="py-3 pr-4 font-medium">Sessions Scored</th>
                    <th className="py-3 pr-4 font-medium">Trend</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/10">
                  {leaderboard.map((row, index) => {
                    const scores = salespersonScores[row.name] ?? [];
                    const trend = calculateScoreTrend(scores);
                    const isExpanded = expandedName === row.name;

                    return (
                      <tr key={row.name} className="align-top">
                        <td className="py-3 pr-4 text-zinc-400">{index + 1}</td>
                        <td className="py-3 pr-4">
                          <button
                            type="button"
                            onClick={() => void toggleSalesperson(row.name)}
                            className="font-medium text-zinc-100 transition hover:text-[var(--mk-gold-light)]"
                          >
                            {row.name}
                          </button>
                          {isExpanded ? (
                            <RecentScoreList scores={scores.slice(0, 10)} />
                          ) : null}
                        </td>
                        <td className="py-3 pr-4 font-semibold tabular-nums text-[var(--mk-gold)]">
                          {Number(row.avg_overall).toFixed(1)}
                        </td>
                        <td className="py-3 pr-4 tabular-nums text-zinc-300">
                          {row.session_count}
                        </td>
                        <td className="py-3 pr-4">
                          <TrendBadge trend={trend} />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  );
}

function RecentScoreList({ scores }: { scores: SessionScore[] }) {
  if (scores.length === 0) {
    return <p className="mt-3 text-xs text-zinc-500">Loading recent sessions...</p>;
  }

  return (
    <div className="mt-3 grid max-w-xl gap-2">
      {scores.map((score) => (
        <div
          key={score.session_id}
          className="flex items-center justify-between gap-3 rounded-md border border-white/10 bg-black/25 px-3 py-2 text-xs"
        >
          <span className="text-zinc-400">{formatTimestamp(score.created_at)}</span>
          <span className="font-semibold tabular-nums text-zinc-100">
            {Number(score.overall_score).toFixed(1)} / 10
          </span>
        </div>
      ))}
    </div>
  );
}

function calculateScoreTrend(scores: SessionScore[]) {
  if (scores.length < 6) {
    return 0;
  }

  const recent = scores.slice(0, 5);
  const previous = scores.slice(5, 10);
  if (previous.length === 0) {
    return 0;
  }

  return averageScore(recent) - averageScore(previous);
}

function averageScore(scores: SessionScore[]) {
  if (scores.length === 0) {
    return 0;
  }
  return scores.reduce((total, score) => total + Number(score.overall_score || 0), 0) / scores.length;
}

function TrendBadge({ trend }: { trend: number }) {
  if (trend > 0.2) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-emerald-300/20 bg-emerald-400/10 px-2.5 py-1 text-xs text-emerald-100">
        <TrendingUp className="size-3.5" />
        Up
      </span>
    );
  }

  if (trend < -0.2) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-red-300/20 bg-red-400/10 px-2.5 py-1 text-xs text-red-100">
        <TrendingDown className="size-3.5" />
        Down
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-xs text-zinc-300">
      <Minus className="size-3.5" />
      Flat
    </span>
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
  onBack,
  onDeleteSession,
  onSaveFeedback,
  onSelectSession,
  onGenerateSessionScore,
  savedFeedbackIds,
  salesperson,
  sessionScore,
  selectedSession,
  isGeneratingSessionScore,
  stats,
  store,
  storeSessions,
}: {
  events: SessionEvent[];
  onBack: () => void;
  onDeleteSession: (sessionId: string) => Promise<void>;
  onSaveFeedback: (eventId: number, feedback: FeedbackValue) => Promise<void>;
  onSelectSession: (session: Session) => Promise<void>;
  onGenerateSessionScore: () => Promise<void>;
  savedFeedbackIds: Set<number>;
  salesperson: Salesperson;
  sessionScore: SessionScore | null;
  selectedSession: Session | null;
  isGeneratingSessionScore: boolean;
  stats: Stats;
  store: Store;
  storeSessions: Session[];
}) {
  const salespersonSessions = sortSessionsNewestFirst(
    storeSessions.filter((session) =>
      sessionBelongsToSalesperson(session, salesperson),
    ),
  );
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(null);
  const [deletingSessionId, setDeletingSessionId] = useState<string | null>(null);
  const [deleteMessage, setDeleteMessage] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [conversationMode, setConversationMode] = useState<ConversationMode>("live");
  const transcriptContainerRef = useRef<HTMLDivElement | null>(null);
  const renderedTranscriptIdsRef = useRef<Set<string>>(new Set());
  const scrollSnapshotRef = useRef({ scrollTop: 0, scrollHeight: 0, wasAtBottom: true });
  const fullConversationText = useMemo(
    () =>
      events
        .map((event) => `[${formatTimestamp(event.timestamp)}] ${event.transcript || ""}`.trim())
        .join("\n"),
    [events],
  );

  useEffect(() => {
    renderedTranscriptIdsRef.current = new Set(events.map(eventStableId));
  }, [events]);

  useLayoutEffect(() => {
    const container = transcriptContainerRef.current;
    if (!container) {
      return;
    }

    const { scrollTop, scrollHeight, wasAtBottom } = scrollSnapshotRef.current;
    if (wasAtBottom) {
      container.scrollTop = container.scrollHeight;
      return;
    }

    const heightDelta = container.scrollHeight - scrollHeight;
    container.scrollTop = scrollTop + heightDelta;
  }, [events, conversationMode]);

  useLayoutEffect(() => {
    return () => {
      const container = transcriptContainerRef.current;
      if (!container) {
        return;
      }

      scrollSnapshotRef.current = {
        scrollTop: container.scrollTop,
        scrollHeight: container.scrollHeight,
        wasAtBottom:
          container.scrollHeight - container.scrollTop - container.clientHeight <= 100,
      };
    };
  }, [events, conversationMode]);

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
                <h2 className="font-semibold text-zinc-100">
                  {conversationMode === "live" ? "Live Transcript Feed" : "Full Conversation"}
                </h2>
                <p className="mt-1 text-sm text-zinc-500">
                  {selectedSession
                    ? `Session #${selectedSession.session_id}`
                    : "No session found for this salesperson yet."}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <div className="inline-flex rounded-lg border border-white/10 bg-black/25 p-1">
                  {(["live", "full"] as ConversationMode[]).map((mode) => (
                    <button
                      key={mode}
                      type="button"
                      onClick={() => setConversationMode(mode)}
                      className={cn(
                        "min-h-8 rounded-md px-3 text-xs font-medium transition",
                        conversationMode === mode
                          ? "bg-[var(--mk-gold)] text-[var(--mk-dark)]"
                          : "text-zinc-400 hover:bg-white/[0.04] hover:text-zinc-100",
                      )}
                    >
                      {mode === "live" ? "Live Feed" : "Full Conversation"}
                    </button>
                  ))}
                </div>
                {conversationMode === "full" && selectedSession ? (
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => void navigator.clipboard.writeText(fullConversationText)}
                    className="min-h-9 border-white/10 bg-transparent text-xs text-zinc-300 hover:border-[var(--mk-gold)]/50 hover:bg-[var(--mk-gold)]/10 hover:text-[var(--mk-gold-light)]"
                  >
                    Copy All
                  </Button>
                ) : null}
              </div>
            </div>

            <div
              ref={transcriptContainerRef}
              className="max-h-[62vh] space-y-3 overflow-y-auto p-4 lg:max-h-[calc(100vh-330px)]"
            >
              <SessionScoreCard
                isGenerating={isGeneratingSessionScore}
                onGenerate={onGenerateSessionScore}
                score={sessionScore}
                selectedSession={selectedSession}
              />

              {!selectedSession ? (
                <EmptyState>No transcript session exists for this salesperson yet.</EmptyState>
              ) : events.length === 0 ? (
                <EmptyState>No transcript events for this session yet.</EmptyState>
              ) : conversationMode === "full" ? (
                <div className="space-y-3 rounded-lg border border-white/10 bg-black/25 p-4">
                  {events.map((event, index) => (
                    <p
                      key={eventStableId(event, index)}
                      className="text-sm leading-7 text-zinc-100"
                    >
                      <time className="mr-2 text-xs text-zinc-500">
                        {formatTimestamp(event.timestamp)}
                      </time>
                      {event.transcript || "No transcript text captured."}
                    </p>
                  ))}
                </div>
              ) : (
                events.map((event, index) => (
                  <TranscriptCard
                    key={eventStableId(event, index)}
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

function SessionScoreCard({
  isGenerating,
  onGenerate,
  score,
  selectedSession,
}: {
  isGenerating: boolean;
  onGenerate: () => Promise<void>;
  score: SessionScore | null;
  selectedSession: Session | null;
}) {
  return (
    <section className="rounded-lg border border-white/10 bg-black/25 p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="text-sm font-semibold text-zinc-100">Session Score</h3>
          {score ? (
            <p className="mt-1 text-4xl font-semibold tabular-nums text-[var(--mk-gold)]">
              {Number(score.overall_score).toFixed(1)} / 10
            </p>
          ) : (
            <p className="mt-2 text-sm text-zinc-500">
              {selectedSession ? "Score pending" : "No session selected"}
            </p>
          )}
        </div>
        <Button
          type="button"
          variant="outline"
          disabled={!selectedSession || isGenerating}
          onClick={() => void onGenerate()}
          className="min-h-9 border-white/10 bg-transparent text-xs text-zinc-300 hover:border-[var(--mk-gold)]/50 hover:bg-[var(--mk-gold)]/10 hover:text-[var(--mk-gold-light)] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isGenerating ? "Generating" : "Generate Score Now"}
        </Button>
      </div>

      {score ? (
        <>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {scoreDimensions.map((dimension) => (
              <ScoreBar
                key={dimension.key}
                label={dimension.label}
                value={Number(score[dimension.key] ?? 0)}
              />
            ))}
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-3 text-xs text-zinc-500">
            <span>Customer Satisfaction: {score.customer_satisfaction ?? "Neutral"}</span>
            {score.created_at ? <span>Scored {formatTimestamp(score.created_at)}</span> : null}
          </div>
          {score.score_reasoning ? (
            <p className="mt-3 text-sm italic leading-6 text-zinc-400">
              {score.score_reasoning}
            </p>
          ) : null}
        </>
      ) : (
        <p className="mt-2 text-xs text-zinc-500">
          Scores are generated when the session ends
        </p>
      )}
    </section>
  );
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  const clampedValue = Math.max(0, Math.min(Number(value) || 0, 10));
  const fillClass = clampedValue >= 7
    ? "bg-[var(--mk-gold)]"
    : clampedValue >= 5
      ? "bg-amber-300"
      : "bg-red-400";

  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.035] p-3">
      <div className="flex items-start justify-between gap-3">
        <span className="text-sm text-zinc-300">{label}</span>
        <span className="font-semibold tabular-nums text-zinc-100">{clampedValue} / 10</span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10">
        <div
          className={cn("h-full rounded-full", fillClass)}
          style={{ width: `${clampedValue * 10}%` }}
        />
      </div>
    </div>
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
          <span>{session.event_count ?? 0} events</span>
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
