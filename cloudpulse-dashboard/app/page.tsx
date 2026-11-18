"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type User = { id: number; username: string; email: string; full_name: string; role: string };
type Metrics = {
  cpu_usage_percent: number;
  memory_usage_percent: number;
  disk_usage_percent: number;
  latency_ms: number | null;
  error_rate_percent: number | null;
  request_rate: number | null;
  timestamp: string;
};
type Summary = {
  instance_id: string;
  latest_metrics: Metrics;
  incidents: { open: number; total: number };
  ml_detection?: { is_trained: boolean; model_version: string; latest: { is_anomaly: boolean; anomaly_score: number; detected_at: string } | null };
};
type Metric = Metrics & { id: number; instance_id: string };
type Instance = {
  instance_id: string;
  last_seen: string;
  cpu_usage_percent: number;
  memory_usage_percent: number;
  disk_usage_percent: number;
  sample_count: number;
  open_incidents: number;
};
type Incident = {
  id: number;
  instance_id: string;
  metric_id: number | null;
  incident_type: string;
  severity: string;
  title: string;
  description: string;
  metric_value: number;
  threshold_value: number;
  status: string;
  detected_at: string;
  resolved_at: string | null;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
};
type Event = { id: number; event_type: string; event_message: string; metadata: Record<string, unknown> | null; event_timestamp: string };
type Replay = Incident & { timeline: Event[] };
type MLStatus = {
  is_trained: boolean;
  model_version: string;
  model_type: string;
  training_samples: number | null;
  trained_at: string | null;
  detection_count: number;
  anomaly_count: number;
  latest: { instance_id: string; metric_id: number; is_anomaly: boolean; anomaly_score: number; detected_at: string } | null;
};
type Anomaly = { id: number; instance_id: string; metric_id: number; is_anomaly: boolean; anomaly_score: number; model_version: string; features: Record<string, number>; detected_at: string };
type CostRecommendation = { instance_id: string; sample_count: number; average_cpu_percent: number; peak_cpu_percent: number; average_memory_percent: number; peak_memory_percent: number; status: string; recommended_action: string; reason: string };
type Notification = { id: number; incident_id: number | null; instance_id: string | null; channel: string; status: string; provider_reference: string | null; details: Record<string, unknown>; created_at: string };
type Thresholds = { cpu: { warning: number; critical: number }; memory: { warning: number; critical: number }; disk: { warning: number; critical: number } };
type Tab = "overview" | "incidents" | "ml" | "settings";

const API = "/api/backend/v1";

async function api<T>(path: string, token?: string | null, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(`${API}${path}`, { ...init, headers, cache: "no-store" });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      // Keep the HTTP fallback when the server did not return JSON.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

const initialThresholds: Thresholds = {
  cpu: { warning: 80, critical: 95 },
  memory: { warning: 80, critical: 95 },
  disk: { warning: 80, critical: 95 },
};

function Panel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-2xl border border-slate-800/90 bg-slate-900/75 p-5 shadow-xl shadow-black/10 ${className}`}>{children}</section>;
}

function SectionTitle({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        {eyebrow && <p className="mb-1 text-[10px] font-bold uppercase tracking-[0.22em] text-cyan-400">{eyebrow}</p>}
        <h2 className="text-lg font-semibold tracking-tight text-white">{title}</h2>
        {description && <p className="mt-1 text-sm text-slate-400">{description}</p>}
      </div>
      {action}
    </div>
  );
}

function MetricCard({ label, value, unit, note, accent, icon }: { label: string; value: string; unit?: string; note: string; accent: string; icon: string }) {
  return (
    <Panel className="relative overflow-hidden">
      <div className={`absolute right-0 top-0 h-24 w-24 rounded-full ${accent} opacity-[0.08] blur-2xl`} />
      <div className="relative flex items-start justify-between">
        <div>
          <p className="text-xs font-medium text-slate-400">{label}</p>
          <p className="mt-3 text-3xl font-semibold tracking-tight text-white">{value}<span className="ml-1 text-sm font-medium text-slate-400">{unit}</span></p>
          <p className="mt-2 text-[11px] text-slate-500">{note}</p>
        </div>
        <span className={`grid h-10 w-10 place-items-center rounded-xl ${accent} bg-opacity-10 text-lg`} aria-hidden="true">{icon}</span>
      </div>
    </Panel>
  );
}

function Pill({ children, tone = "slate" }: { children: ReactNode; tone?: "slate" | "green" | "amber" | "red" | "blue" }) {
  const tones = {
    slate: "border-slate-700 bg-slate-800/80 text-slate-300",
    green: "border-emerald-500/20 bg-emerald-500/10 text-emerald-300",
    amber: "border-amber-500/20 bg-amber-500/10 text-amber-300",
    red: "border-rose-500/20 bg-rose-500/10 text-rose-300",
    blue: "border-cyan-500/20 bg-cyan-500/10 text-cyan-300",
  };
  return <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide ${tones[tone]}`}>{children}</span>;
}

function severityTone(severity: string): "red" | "amber" | "blue" {
  const value = severity.toLowerCase();
  return value === "critical" ? "red" : value === "warning" ? "amber" : "blue";
}

export default function Home() {
  const [tab, setTab] = useState<Tab>("overview");
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loginOpen, setLoginOpen] = useState(false);
  const [loginError, setLoginError] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [lastRefresh, setLastRefresh] = useState<string | null>(null);
  const [refreshRate, setRefreshRate] = useState(15000);
  const [instanceFilter, setInstanceFilter] = useState("all");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [instances, setInstances] = useState<Instance[]>([]);
  const [history, setHistory] = useState<Metric[]>([]);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [selectedIncident, setSelectedIncident] = useState<Incident | null>(null);
  const [incidentReplay, setIncidentReplay] = useState<Replay | null>(null);
  const [ml, setMl] = useState<MLStatus | null>(null);
  const [anomalies, setAnomalies] = useState<Anomaly[]>([]);
  const [costRecommendations, setCostRecommendations] = useState<CostRecommendation[]>([]);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [thresholds, setThresholds] = useState<Thresholds>(initialThresholds);
  const [thresholdSaved, setThresholdSaved] = useState("");
  const [incidentStatusFilter, setIncidentStatusFilter] = useState("all");

  useEffect(() => {
    const saved = window.sessionStorage.getItem("cloudpulse_token");
    if (!saved) return;
    api<User>("/auth/me", saved).then((profile) => {
      setToken(saved);
      setUser(profile);
    }).catch(() => {
      window.sessionStorage.removeItem("cloudpulse_token");
    });
  }, []);

  const loadDashboard = useCallback(async () => {
    const scope = instanceFilter === "all" ? "" : `&instance_id=${encodeURIComponent(instanceFilter)}`;
    const summaryPath = instanceFilter === "all" ? "/dashboard/summary" : `/dashboard/summary?instance_id=${encodeURIComponent(instanceFilter)}`;
    const historyPath = `/metrics/history?limit=120${scope}`;
    const incidentsPath = `/incidents?limit=100${scope}`;
    const results = await Promise.allSettled([
      api<Summary>(summaryPath),
      api<{ instances: Instance[] }>("/instances"),
      api<{ metrics: Metric[] }>(historyPath),
      api<{ incidents: Incident[] }>(incidentsPath),
      api<MLStatus>("/ml/status"),
      api<{ anomalies: Anomaly[] }>(`/anomalies?limit=30${scope}`),
      api<{ recommendations: CostRecommendation[] }>("/cost/recommendations?days=7"),
      api<{ notifications: Notification[] }>("/notifications?limit=30"),
      api<{ thresholds: Thresholds }>("/settings/thresholds"),
    ]);

    const [summaryResult, instancesResult, historyResult, incidentResult, mlResult, anomaliesResult, costResult, notificationsResult, thresholdsResult] = results;
    if (summaryResult.status === "fulfilled") setSummary(summaryResult.value);
    else setSummary(null);
    if (instancesResult.status === "fulfilled") setInstances(instancesResult.value.instances ?? []);
    if (historyResult.status === "fulfilled") setHistory(historyResult.value.metrics ?? []);
    if (incidentResult.status === "fulfilled") setIncidents(incidentResult.value.incidents ?? []);
    if (mlResult.status === "fulfilled") setMl(mlResult.value);
    if (anomaliesResult.status === "fulfilled") setAnomalies(anomaliesResult.value.anomalies ?? []);
    if (costResult.status === "fulfilled") setCostRecommendations(costResult.value.recommendations ?? []);
    if (notificationsResult.status === "fulfilled") setNotifications(notificationsResult.value.notifications ?? []);
    if (thresholdsResult.status === "fulfilled") setThresholds(thresholdsResult.value.thresholds ?? initialThresholds);

    if (summaryResult.status === "rejected") {
      setError(summaryResult.reason instanceof Error ? summaryResult.reason.message : "Unable to load dashboard summary");
    } else {
      setError("");
    }
    setLastRefresh(new Date().toISOString());
  }, [instanceFilter]);

  useEffect(() => {
    const initialLoad = window.setTimeout(() => {
      void loadDashboard();
    }, 0);

    if (refreshRate === 0) {
      return () => window.clearTimeout(initialLoad);
    }

    const timer = window.setInterval(() => void loadDashboard(), refreshRate);

    return () => {
      window.clearTimeout(initialLoad);
      window.clearInterval(timer);
    };
  }, [loadDashboard, refreshRate]);

  const openIncident = async (incident: Incident) => {
    setSelectedIncident(incident);
    setIncidentReplay(null);
    try {
      const replay = await api<Replay>(`/incidents/${incident.id}/replay`, token);
      setIncidentReplay(replay);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load incident timeline");
    }
  };

  const submitLogin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setLoginError("");
    try {
      const result = await api<{ access_token: string; user: User }>("/auth/login", null, {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      window.sessionStorage.setItem("cloudpulse_token", result.access_token);
      setToken(result.access_token);
      setUser(result.user);
      setPassword("");
      setLoginOpen(false);
      await loadDashboard();
    } catch (err) {
      setLoginError(err instanceof Error ? err.message : "Sign-in failed");
    } finally {
      setBusy(false);
    }
  };

  const logout = () => {
    window.sessionStorage.removeItem("cloudpulse_token");
    setToken(null);
    setUser(null);
  };

  const incidentAction = async (incident: Incident, action: "acknowledge" | "resolve") => {
    if (!token) {
      setLoginOpen(true);
      setLoginError("Sign in as an analyst or admin to manage incidents.");
      return;
    }
    setBusy(true);
    try {
      const result = await api<{ incident?: Partial<Incident> }>(
        `/incidents/${incident.id}/${action}`,
        token,
        { method: "PATCH" },
      );
      await loadDashboard();
      if (selectedIncident?.id === incident.id) {
        const updatedIncident = { ...incident, ...(result.incident ?? {}) };
        setSelectedIncident(updatedIncident);
        const replay = await api<Replay>(`/incidents/${incident.id}/replay`, token);
        setIncidentReplay(replay);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : `Unable to ${action} incident`);
    } finally {
      setBusy(false);
    }
  };

  const collectNow = async () => {
    setBusy(true);
    try {
      await api("/metrics/collect", token, { method: "POST" });
      await loadDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Metric collection failed");
    } finally {
      setBusy(false);
    }
  };

  const retrainModel = async () => {
    if (!token) {
      setLoginOpen(true);
      setLoginError("Sign in as an analyst or admin to retrain the model.");
      return;
    }
    setBusy(true);
    try {
      const result = await api<{ message: string; samples: number }>("/ml/train", token, { method: "POST" });
      setThresholdSaved(`Model trained with ${result.samples} historical samples.`);
      await loadDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Model training failed");
    } finally {
      setBusy(false);
    }
  };

  const saveThresholds = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (user?.role !== "admin" || !token) {
      setLoginOpen(true);
      setLoginError("Administrator sign-in is required to change alert thresholds.");
      return;
    }
    setBusy(true);
    setThresholdSaved("");
    const body = {
      cpu_warning: thresholds.cpu.warning,
      cpu_critical: thresholds.cpu.critical,
      memory_warning: thresholds.memory.warning,
      memory_critical: thresholds.memory.critical,
      disk_warning: thresholds.disk.warning,
      disk_critical: thresholds.disk.critical,
    };
    try {
      const result = await api<{ thresholds: Thresholds }>("/settings/thresholds", token, {
        method: "PUT",
        body: JSON.stringify(body),
      });
      setThresholds(result.thresholds);
      setThresholdSaved("Thresholds saved. New metric collections will use these values.");
      await loadDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save thresholds");
    } finally {
      setBusy(false);
    }
  };

  const chartInstances = useMemo(
    () => [...new Set(history.map((metric) => metric.instance_id))].sort(),
    [history],
  );

  const chartSeries = useMemo(() => {
    const resources = [
      { key: "cpu", label: "CPU", colorIndex: 0 },
      { key: "memory", label: "Memory", colorIndex: 1 },
      { key: "disk", label: "Disk", colorIndex: 2 },
    ] as const;

    const instancePalettes = [
      ["#22d3ee", "#818cf8", "#34d399"],
      ["#fb923c", "#c084fc", "#facc15"],
      ["#f472b6", "#60a5fa", "#a3e635"],
      ["#f87171", "#2dd4bf", "#e879f9"],
      ["#a78bfa", "#fb7185", "#38bdf8"],
    ];

    return chartInstances.flatMap((instanceId, instanceIndex) => {
      const palette = instancePalettes[instanceIndex % instancePalettes.length];
      const displayName =
        instanceId === "local-docker"
          ? "Local Docker"
          : instanceId.startsWith("i-")
            ? `EC2 ${instanceId.slice(-5)}`
            : instanceId;

      return resources.map((resource) => ({
        dataKey: `instance_${instanceIndex}_${resource.key}`,
        name: `${displayName} · ${resource.label}`,
        stroke: palette[resource.colorIndex],
      }));
    });
  }, [chartInstances]);

  const chartData = useMemo(() => {
    const instanceIndexes = new Map(
      chartInstances.map((instanceId, index) => [instanceId, index] as const),
    );

    return [...history]
      .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
      .map((metric) => {
        const row: Record<string, string | number | null> = {
          time: new Date(metric.timestamp).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          }),
        };

        chartInstances.forEach((_, index) => {
          row[`instance_${index}_cpu`] = null;
          row[`instance_${index}_memory`] = null;
          row[`instance_${index}_disk`] = null;
        });

        const instanceIndex = instanceIndexes.get(metric.instance_id);

        if (instanceIndex !== undefined) {
          row[`instance_${instanceIndex}_cpu`] = metric.cpu_usage_percent;
          row[`instance_${instanceIndex}_memory`] = metric.memory_usage_percent;
          row[`instance_${instanceIndex}_disk`] = metric.disk_usage_percent;
        }

        return row;
      });
  }, [history, chartInstances]);

  const current = summary?.latest_metrics;
  const healthScore = current
    ? Math.round(100 - Math.min(100, current.cpu_usage_percent * 0.25 + current.memory_usage_percent * 0.2 + (current.latency_ms ?? 0) / 10 * 0.2 + (current.error_rate_percent ?? 0) * 0.2 + (current.request_rate ?? 0) * 15))
    : null;
  const healthTone = healthScore === null ? "slate" : healthScore >= 80 ? "green" : healthScore >= 60 ? "amber" : "red";
  const openIncidents = summary?.incidents.open ?? incidents.filter((incident) => incident.status === "open").length;
  const criticalIncidents = incidents.filter((incident) => incident.status === "open" && incident.severity.toLowerCase() === "critical").length;
  const visibleIncidents = incidentStatusFilter === "all" ? incidents : incidents.filter((incident) => incident.status === incidentStatusFilter);

  const updateThreshold = (metric: keyof Thresholds, kind: "warning" | "critical", value: string) => {
    const parsed = Number(value);
    setThresholds((currentValue) => ({
      ...currentValue,
      [metric]: { ...currentValue[metric], [kind]: Number.isFinite(parsed) ? parsed : 0 },
    }));
  };

  return (
    <main className="min-h-screen bg-[#070b14] text-slate-100">
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -left-40 -top-40 h-[32rem] w-[32rem] rounded-full bg-cyan-500/[0.06] blur-3xl" />
        <div className="absolute right-0 top-1/3 h-[28rem] w-[28rem] rounded-full bg-blue-500/[0.05] blur-3xl" />
      </div>
      <div className="relative mx-auto flex min-h-screen max-w-[1600px] flex-col lg:flex-row">
        <aside className="border-b border-slate-800 bg-[#0a1020]/90 p-4 backdrop-blur-xl lg:sticky lg:top-0 lg:h-screen lg:w-64 lg:shrink-0 lg:border-b-0 lg:border-r lg:p-5">
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-cyan-400 to-blue-600 text-lg font-black text-slate-950 shadow-lg shadow-cyan-500/20">C</div>
            <div>
              <p className="text-sm font-bold tracking-wide text-white">CLOUDPULSE</p>
              <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-cyan-400">Sentinel / AIOps</p>
            </div>
          </div>
          <div className="mt-8 hidden lg:block">
            <p className="mb-3 px-3 text-[10px] font-bold uppercase tracking-[0.2em] text-slate-600">Workspace</p>
            <nav className="space-y-1" aria-label="Dashboard sections">
              {([
                ["overview", "◫", "Overview"],
                ["incidents", "⚑", "Incidents"],
                ["ml", "✳", "ML & Cost"],
                ["settings", "⚙", "Settings"],
              ] as [Tab, string, string][]).map(([key, icon, label]) => (
                <button key={key} onClick={() => setTab(key)} className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm transition ${tab === key ? "bg-cyan-400/10 font-semibold text-cyan-300 ring-1 ring-cyan-400/20" : "text-slate-400 hover:bg-slate-800/70 hover:text-white"}`}>
                  <span className="w-5 text-center text-base">{icon}</span>{label}
                  {key === "incidents" && openIncidents > 0 && <span className="ml-auto rounded-full bg-rose-500/15 px-2 py-0.5 text-[10px] text-rose-300">{openIncidents}</span>}
                </button>
              ))}
            </nav>
          </div>
          <div className="mt-4 flex gap-2 overflow-x-auto lg:hidden">
            {([
              ["overview", "Overview"], ["incidents", "Incidents"], ["ml", "ML & Cost"], ["settings", "Settings"],
            ] as [Tab, string][]).map(([key, label]) => <button key={key} onClick={() => setTab(key)} className={`whitespace-nowrap rounded-lg px-3 py-2 text-xs font-semibold ${tab === key ? "bg-cyan-400/15 text-cyan-200" : "bg-slate-900 text-slate-400"}`}>{label}</button>)}
          </div>
          <div className="mt-8 hidden rounded-xl border border-slate-800 bg-slate-900/70 p-4 lg:block">
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-300"><span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_10px_#34d399]" /> API workspace</div>
            <p className="mt-2 text-[11px] leading-5 text-slate-500">Local-first monitoring. Cloud delivery channels activate when configured.</p>
            <p className="mt-3 break-all font-mono text-[10px] text-slate-600">{instanceFilter === "all" ? `${instances.length} instances` : instanceFilter}</p>
          </div>
          <div className="mt-8 border-t border-slate-800 pt-4 lg:mt-auto lg:border-0">
            {user ? (
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0"><p className="truncate text-xs font-semibold text-white">{user.full_name || user.username}</p><p className="text-[10px] uppercase tracking-wider text-slate-500">{user.role}</p></div>
                <button onClick={logout} className="rounded-lg border border-slate-700 px-2.5 py-1.5 text-[10px] text-slate-400 hover:border-slate-500 hover:text-white">Sign out</button>
              </div>
            ) : (
              <button onClick={() => setLoginOpen((value) => !value)} className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2.5 text-xs font-semibold text-slate-200 hover:border-cyan-400/40 hover:text-cyan-200">Sign in for actions</button>
            )}
          </div>
        </aside>

        <section className="min-w-0 flex-1 p-4 sm:p-6 lg:p-8">
          <header className="mb-7 flex flex-col justify-between gap-4 border-b border-slate-800/80 pb-6 sm:flex-row sm:items-end">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.24em] text-cyan-400">Operations command center</p>
              <h1 className="mt-2 text-2xl font-semibold tracking-tight text-white sm:text-3xl">{tab === "overview" ? "Infrastructure overview" : tab === "incidents" ? "Incident management" : tab === "ml" ? "Intelligence & optimization" : "Platform settings"}</h1>
              <p className="mt-1 text-sm text-slate-500">{tab === "overview" ? "Live health, resource utilization and fleet visibility." : tab === "incidents" ? "Triage, acknowledge and resolve operational events." : tab === "ml" ? "Model transparency, anomaly history and utilization insights." : "Tune alert thresholds and review notification delivery."}</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <label className="sr-only" htmlFor="instance-filter">Instance filter</label>
              <select id="instance-filter" value={instanceFilter} onChange={(event) => setInstanceFilter(event.target.value)} className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2.5 text-xs text-slate-200 outline-none focus:border-cyan-400">
                <option value="all">All instances</option>
                {instances.map((instance) => <option key={instance.instance_id} value={instance.instance_id}>{instance.instance_id}</option>)}
              </select>
              <label className="sr-only" htmlFor="refresh-rate">Refresh interval</label>
              <select id="refresh-rate" value={refreshRate} onChange={(event) => setRefreshRate(Number(event.target.value))} className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2.5 text-xs text-slate-200 outline-none focus:border-cyan-400">
                <option value={10000}>Refresh · 10s</option><option value={15000}>Refresh · 15s</option><option value={30000}>Refresh · 30s</option><option value={0}>Refresh · off</option>
              </select>
              <button onClick={() => void collectNow()} disabled={busy} className="rounded-xl border border-emerald-400/30 bg-emerald-400/10 px-3 py-2.5 text-xs font-semibold text-emerald-200 hover:bg-emerald-400/15 disabled:opacity-50">＋ Collect now</button>
              <button onClick={() => void loadDashboard()} className="rounded-xl border border-cyan-400/30 bg-cyan-400/10 px-3 py-2.5 text-xs font-semibold text-cyan-200 hover:bg-cyan-400/15">↻ Refresh</button>
            </div>
          </header>

          {error && <div role="alert" className="mb-5 flex items-center justify-between gap-3 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200"><span>{error}</span><button onClick={() => setError("")} className="text-rose-300">Dismiss</button></div>}
          {loginOpen && (
            <Panel className="mb-6 border-cyan-500/30">
              <div className="mb-3 flex items-center justify-between"><div><p className="text-sm font-semibold text-white">Sign in to CloudPulse</p><p className="text-xs text-slate-500">Incident actions and model retraining require an authorized account.</p></div><button onClick={() => setLoginOpen(false)} className="text-slate-500 hover:text-white" aria-label="Close sign in">✕</button></div>
              <form onSubmit={submitLogin} className="grid gap-3 sm:grid-cols-[1fr_1fr_auto]">
                <input value={username} onChange={(event) => setUsername(event.target.value)} placeholder="Username" autoComplete="username" required className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm outline-none focus:border-cyan-400" />
                <input value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Password" type="password" autoComplete="current-password" required className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm outline-none focus:border-cyan-400" />
                <button disabled={busy} className="rounded-xl bg-cyan-400 px-5 py-2.5 text-sm font-bold text-slate-950 disabled:opacity-50">{busy ? "Signing in…" : "Sign in"}</button>
              </form>
              {loginError && <p className="mt-2 text-xs text-rose-300">{loginError}</p>}
            </Panel>
          )}

          {tab === "overview" && (
            <div className="space-y-6">
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                <MetricCard label="Infrastructure health" value={healthScore === null ? "—" : String(healthScore)} unit="/ 100" note={healthTone === "green" ? "Heuristic indicator · healthy range" : healthTone === "amber" ? "Heuristic indicator · monitor pressure" : healthTone === "red" ? "Heuristic indicator · operator attention" : "Waiting for telemetry"} accent="bg-cyan-400" icon="◈" />
                <MetricCard label="Open incidents" value={String(openIncidents)} note={`${criticalIncidents} critical · ${incidents.length} in current view`} accent="bg-rose-400" icon="⚑" />
                <MetricCard label="Monitored instances" value={String(instances.length)} note="Instances with at least one stored sample" accent="bg-blue-400" icon="▤" />
                <MetricCard label="ML anomaly events" value={String(ml?.anomaly_count ?? 0)} note={ml?.is_trained ? `Model ${ml.model_version} active` : "Model training required"} accent="bg-violet-400" icon="✳" />
              </div>

              <div className="grid gap-4 xl:grid-cols-[1.7fr_1fr]">
                <Panel>
                  <SectionTitle eyebrow="Resource telemetry" title="Utilization over time" description={`${history.length} stored samples · ${instanceFilter === "all" ? "all instances" : instanceFilter}`} action={<Pill tone="blue">Auto refresh {refreshRate === 0 ? "off" : `${refreshRate / 1000}s`}</Pill>} />
                  <div className="h-[300px] w-full">
                    {chartData.length ? <ResponsiveContainer width="100%" height="100%"><LineChart data={chartData} margin={{ top: 8, right: 12, left: -18, bottom: 0 }}>
                      <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="time" tick={{ fill: "#64748b", fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={24} />
                      <YAxis domain={[0, 100]} tick={{ fill: "#64748b", fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={(value) => `${value}%`} />
                      <Tooltip contentStyle={{ background: "#0b1220", border: "1px solid #334155", borderRadius: 12, color: "#e2e8f0" }} formatter={(value) => [`${Number(value).toFixed(1)}%`]} />
                      <Legend wrapperStyle={{ color: "#94a3b8", fontSize: 11 }} />
                      {chartSeries.map((series) => (
                        <Line
                          key={series.dataKey}
                          type="monotone"
                          dataKey={series.dataKey}
                          name={series.name}
                          stroke={series.stroke}
                          strokeWidth={2.5}
                          dot={false}
                          activeDot={{ r: 4 }}
                          connectNulls
                        />
                      ))}
                    </LineChart></ResponsiveContainer> : <div className="grid h-full place-items-center rounded-xl border border-dashed border-slate-800 text-sm text-slate-500">No metric history yet. Collect metrics or connect an instance agent.</div>}
                  </div>
                </Panel>
                <Panel>
                  <SectionTitle eyebrow="Current snapshot" title={summary?.instance_id ?? "Awaiting telemetry"} description={current ? `Last sample ${new Date(current.timestamp).toLocaleTimeString()}` : "No sample available for this filter"} />
                  <div className="space-y-5">
                    {([
                      ["CPU", current?.cpu_usage_percent, "#22d3ee"],
                      ["Memory", current?.memory_usage_percent, "#818cf8"],
                      ["Disk", current?.disk_usage_percent, "#34d399"],
                    ] as [string, number | undefined, string][]).map(([label, value, color]) => <div key={label}>
                      <div className="mb-2 flex justify-between text-xs"><span className="text-slate-400">{label}</span><span className="font-semibold text-slate-200">{value === undefined ? "—" : `${value.toFixed(1)}%`}</span></div>
                      <div className="h-2 overflow-hidden rounded-full bg-slate-800"><div className="h-full rounded-full transition-all" style={{ width: `${Math.max(0, Math.min(100, value ?? 0))}%`, backgroundColor: color }} /></div>
                    </div>)}
                    <div className="grid grid-cols-2 gap-3 border-t border-slate-800 pt-4">
                      <div><p className="text-[10px] uppercase tracking-wider text-slate-500">API latency</p><p className="mt-1 text-lg font-semibold text-white">{current?.latency_ms == null ? "—" : `${current.latency_ms} ms`}</p></div>
                      <div><p className="text-[10px] uppercase tracking-wider text-slate-500">Error rate</p><p className="mt-1 text-lg font-semibold text-white">{current?.error_rate_percent == null ? "—" : `${current.error_rate_percent}%`}</p></div>
                    </div>
                  </div>
                </Panel>
              </div>

              <Panel>
                <SectionTitle eyebrow="Fleet inventory" title="Monitored instances" description="Latest resource readings per reporting instance." action={<Pill>{instances.length} registered</Pill>} />
                {instances.length === 0 ? <p className="text-sm text-slate-500">No instances have reported metrics yet. Configure an instance agent to populate this list.</p> : <div className="overflow-x-auto"><table className="w-full min-w-[700px] text-left text-xs"><thead className="border-b border-slate-800 text-[10px] uppercase tracking-wider text-slate-500"><tr><th className="pb-3">Instance</th><th className="pb-3">CPU</th><th className="pb-3">Memory</th><th className="pb-3">Disk</th><th className="pb-3">Open incidents</th><th className="pb-3">Last seen</th></tr></thead><tbody>{instances.map((instance) => <tr key={instance.instance_id} className="border-b border-slate-800/70 last:border-0"><td className="py-3 pr-3 font-mono text-cyan-200">{instance.instance_id}</td><td className="py-3">{instance.cpu_usage_percent.toFixed(1)}%</td><td className="py-3">{instance.memory_usage_percent.toFixed(1)}%</td><td className="py-3">{instance.disk_usage_percent.toFixed(1)}%</td><td className="py-3"><Pill tone={instance.open_incidents ? "amber" : "green"}>{instance.open_incidents}</Pill></td><td className="py-3 text-slate-500">{new Date(instance.last_seen).toLocaleString()}</td></tr>)}</tbody></table></div>}
              </Panel>

              <div className="grid gap-4 xl:grid-cols-2">
                <Panel>
                  <SectionTitle eyebrow="Attention required" title="Recent active incidents" action={<button onClick={() => setTab("incidents")} className="text-xs font-semibold text-cyan-300 hover:text-cyan-200">View all →</button>} />
                  {incidents.filter((item) => item.status === "open").slice(0, 4).length === 0 ? <p className="text-sm text-slate-500">No active incidents in the selected scope.</p> : <div className="space-y-3">{incidents.filter((item) => item.status === "open").slice(0, 4).map((incident) => <button key={incident.id} onClick={() => { setTab("incidents"); void openIncident(incident); }} className="flex w-full items-center gap-3 rounded-xl border border-slate-800 bg-slate-950/60 p-3 text-left transition hover:border-slate-700"><span className={`h-2.5 w-2.5 shrink-0 rounded-full ${incident.severity === "critical" ? "bg-rose-400" : incident.severity === "warning" ? "bg-amber-400" : "bg-cyan-400"}`} /><span className="min-w-0 flex-1"><span className="block truncate text-xs font-semibold text-slate-200">{incident.title}</span><span className="mt-1 block truncate text-[10px] text-slate-500">{incident.instance_id} · {new Date(incident.detected_at).toLocaleString()}</span></span><Pill tone={severityTone(incident.severity)}>{incident.severity}</Pill></button>)}</div>}
                </Panel>
                <Panel>
                  <SectionTitle eyebrow="ML signal" title="Anomaly detection" action={<Pill tone={ml?.is_trained ? "green" : "amber"}>{ml?.is_trained ? "Model active" : "Not trained"}</Pill>} />
                  <div className="grid grid-cols-2 gap-3"><div className="rounded-xl bg-slate-950/70 p-4"><p className="text-[10px] uppercase tracking-wider text-slate-500">Training samples</p><p className="mt-2 text-2xl font-semibold text-white">{ml?.training_samples ?? "—"}</p></div><div className="rounded-xl bg-slate-950/70 p-4"><p className="text-[10px] uppercase tracking-wider text-slate-500">Anomalies detected</p><p className="mt-2 text-2xl font-semibold text-white">{ml?.anomaly_count ?? "—"}</p></div></div>
                  <button onClick={() => setTab("ml")} className="mt-4 text-xs font-semibold text-cyan-300 hover:text-cyan-200">Explore model insights →</button>
                </Panel>
              </div>
              <p className="text-right text-[10px] text-slate-600">Last dashboard refresh: {lastRefresh ? new Date(lastRefresh).toLocaleTimeString() : "—"}</p>
            </div>
          )}

          {tab === "incidents" && (
            <div className="grid gap-5 2xl:grid-cols-[1.35fr_1fr]">
              <Panel>
                <SectionTitle eyebrow="Incident response" title="Incident queue" description={`${incidents.length} incidents in selected scope`} action={<select value={incidentStatusFilter} onChange={(event) => setIncidentStatusFilter(event.target.value)} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-300"><option value="all">All statuses</option><option value="open">Open</option><option value="resolved">Resolved</option></select>} />
                <div className="space-y-2">{visibleIncidents.length === 0 ? <p className="rounded-xl border border-dashed border-slate-800 p-8 text-center text-sm text-slate-500">No incidents match this filter.</p> : visibleIncidents.map((incident) => <button key={incident.id} onClick={() => void openIncident(incident)} className={`w-full rounded-xl border p-4 text-left transition ${selectedIncident?.id === incident.id ? "border-cyan-400/40 bg-cyan-400/[0.06]" : "border-slate-800 bg-slate-950/50 hover:border-slate-700"}`}>
                  <div className="flex flex-wrap items-center justify-between gap-2"><div className="flex items-center gap-2"><Pill tone={severityTone(incident.severity)}>{incident.severity}</Pill><span className="text-[10px] text-slate-600">INC-{incident.id}</span></div><Pill tone={incident.status === "resolved" ? "green" : incident.acknowledged_at ? "blue" : "amber"}>{incident.status === "resolved" ? "Resolved" : incident.acknowledged_at ? "Acknowledged" : "Open"}</Pill></div>
                  <p className="mt-3 text-sm font-semibold text-white">{incident.title}</p><p className="mt-1 text-xs text-slate-500">{incident.instance_id} · {incident.incident_type}</p><p className="mt-2 line-clamp-2 text-xs text-slate-400">{incident.description}</p><p className="mt-3 text-[10px] text-slate-600">{new Date(incident.detected_at).toLocaleString()} · Metric {incident.metric_value}% / threshold {incident.threshold_value}%</p>
                </button>)}</div>
              </Panel>
              <Panel className="h-fit">
                <SectionTitle eyebrow="Event trace" title={selectedIncident ? `Incident #${selectedIncident.id}` : "Select an incident"} description="Detection, acknowledgement, notification and resolution events." />
                {selectedIncident ? <>
                  <p className="text-sm font-semibold text-white">{selectedIncident.title}</p><p className="mt-1 text-xs leading-5 text-slate-400">{selectedIncident.description}</p>
                  <div className="mt-4 grid grid-cols-2 gap-2"><div className="rounded-lg bg-slate-950 p-3"><p className="text-[10px] text-slate-500">Metric value</p><p className="mt-1 text-lg font-semibold">{selectedIncident.metric_value}%</p></div><div className="rounded-lg bg-slate-950 p-3"><p className="text-[10px] text-slate-500">Threshold</p><p className="mt-1 text-lg font-semibold">{selectedIncident.threshold_value}%</p></div></div>
                  {selectedIncident.status === "open" && <div className="mt-4 flex flex-wrap gap-2">{!selectedIncident.acknowledged_at && <button disabled={busy || !token} onClick={() => void incidentAction(selectedIncident, "acknowledge")} className="rounded-lg border border-cyan-400/30 bg-cyan-400/10 px-3 py-2 text-xs font-semibold text-cyan-200 disabled:opacity-40">Acknowledge</button>}<button disabled={busy || !token} onClick={() => void incidentAction(selectedIncident, "resolve")} className="rounded-lg bg-emerald-500/15 px-3 py-2 text-xs font-semibold text-emerald-300 disabled:opacity-40">Resolve incident</button></div>}
                  {!token && <p className="mt-2 text-[10px] text-slate-600">Sign in to enable incident actions.</p>}
                  {selectedIncident.acknowledged_at && <p className="mt-3 text-xs text-cyan-300">Acknowledged by {selectedIncident.acknowledged_by} · {new Date(selectedIncident.acknowledged_at).toLocaleString()}</p>}
                  <div className="mt-6"><p className="mb-4 text-[10px] font-bold uppercase tracking-[0.2em] text-slate-500">Timeline</p>{incidentReplay?.timeline?.length ? <div className="space-y-4">{incidentReplay.timeline.map((event, index) => <div key={event.id} className="relative flex gap-3"><div className="flex flex-col items-center"><span className="mt-1 h-2.5 w-2.5 rounded-full bg-cyan-400 ring-4 ring-cyan-400/10" />{index < (incidentReplay.timeline.length - 1) && <span className="mt-1 h-full w-px bg-slate-800" />}</div><div className="pb-2"><p className="text-xs font-semibold text-slate-200">{event.event_message}</p><p className="mt-1 text-[10px] text-slate-600">{event.event_type.replaceAll("_", " ")} · {new Date(event.event_timestamp).toLocaleString()}</p></div></div>)}</div> : <p className="text-xs text-slate-500">{incidentReplay ? "No timeline events recorded." : "Loading incident timeline…"}</p>}</div>
                </> : <div className="grid min-h-48 place-items-center text-center text-sm text-slate-600">Choose an incident to inspect its timeline and actions.</div>}
              </Panel>
            </div>
          )}

          {tab === "ml" && (
            <div className="space-y-5">
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                <MetricCard label="Model state" value={ml?.is_trained ? "Active" : "Pending"} note={`Isolation Forest · v${ml?.model_version ?? "—"}`} accent="bg-violet-400" icon="✳" />
                <MetricCard label="Training samples" value={ml?.training_samples == null ? "—" : String(ml.training_samples)} note="Samples used by the currently loaded artifact" accent="bg-blue-400" icon="▥" />
                <MetricCard label="Evaluations" value={String(ml?.detection_count ?? 0)} note="Stored model predictions" accent="bg-cyan-400" icon="⌁" />
                <MetricCard label="Anomaly signals" value={String(ml?.anomaly_count ?? 0)} note="Predictions classified as anomalous" accent="bg-rose-400" icon="⚠" />
              </div>
              <div className="grid gap-4 xl:grid-cols-[1fr_1.3fr]">
                <Panel>
                  <SectionTitle eyebrow="Model transparency" title="Model health" description="The anomaly score is a decision-function score, not a probability." action={<Pill tone={ml?.is_trained ? "green" : "amber"}>{ml?.is_trained ? "Trained" : "Training required"}</Pill>} />
                  <div className="space-y-4 text-xs">
                    <div className="flex justify-between border-b border-slate-800 pb-3"><span className="text-slate-500">Algorithm</span><span className="font-medium text-slate-200">Isolation Forest</span></div>
                    <div className="flex justify-between border-b border-slate-800 pb-3"><span className="text-slate-500">Model version</span><span className="font-mono text-slate-200">{ml?.model_version ?? "—"}</span></div>
                    <div className="flex justify-between border-b border-slate-800 pb-3"><span className="text-slate-500">Training date</span><span className="text-right text-slate-200">{ml?.trained_at ? new Date(ml.trained_at).toLocaleString() : "Not recorded"}</span></div>
                    <div className="flex justify-between border-b border-slate-800 pb-3"><span className="text-slate-500">Features</span><span className="text-right text-slate-200">CPU · Memory · Disk</span></div>
                  </div>
                  <button disabled={busy || !token} onClick={() => void retrainModel()} className="mt-5 w-full rounded-xl bg-violet-500/15 px-4 py-3 text-xs font-semibold text-violet-200 transition hover:bg-violet-500/25 disabled:cursor-not-allowed disabled:opacity-40">{busy ? "Working…" : "↻ Retrain on latest 7-day history"}</button>
                  {!token && <p className="mt-2 text-center text-[10px] text-slate-600">Analyst or admin sign-in required.</p>}
                  {thresholdSaved && <p className="mt-3 text-xs text-emerald-300">{thresholdSaved}</p>}
                </Panel>
                <Panel>
                  <SectionTitle eyebrow="Recent predictions" title="Anomaly history" description="Recent model results with their decision scores." />
                  {anomalies.length ? <div className="overflow-x-auto"><table className="w-full min-w-[520px] text-left text-xs"><thead className="text-[10px] uppercase tracking-wider text-slate-500"><tr><th className="pb-3">Result</th><th className="pb-3">Instance</th><th className="pb-3">Score</th><th className="pb-3">Metric ID</th><th className="pb-3">Detected</th></tr></thead><tbody>{anomalies.map((anomaly) => <tr key={anomaly.id} className="border-t border-slate-800"><td className="py-3"><Pill tone={anomaly.is_anomaly ? "red" : "green"}>{anomaly.is_anomaly ? "Anomaly" : "Normal"}</Pill></td><td className="py-3 font-mono text-slate-300">{anomaly.instance_id}</td><td className="py-3 font-mono">{anomaly.anomaly_score.toFixed(5)}</td><td className="py-3 text-slate-400">{anomaly.metric_id}</td><td className="py-3 text-slate-500">{new Date(anomaly.detected_at).toLocaleString()}</td></tr>)}</tbody></table></div> : <p className="text-sm text-slate-500">No anomaly predictions stored yet.</p>}
                  <p className="mt-4 text-[10px] leading-5 text-slate-600">Anomaly classifications depend on the training data. A small or narrow dataset is suitable for a demonstration, not proof of production-grade detection accuracy.</p>
                </Panel>
              </div>
              <Panel>
                <SectionTitle eyebrow="Optimization" title="Cost & resource intelligence" description="Utilization-based recommendations. Dollar savings are not estimated without live pricing and billing inputs." />
                {costRecommendations.length ? <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{costRecommendations.map((item) => <div key={item.instance_id} className="rounded-xl border border-slate-800 bg-slate-950/60 p-4"><div className="flex items-center justify-between gap-2"><p className="truncate text-xs font-semibold text-white">{item.instance_id}</p><Pill tone={item.status === "underutilized" ? "amber" : item.status === "healthy" ? "green" : "slate"}>{item.status.replaceAll("_", " ")}</Pill></div><p className="mt-3 text-xs text-slate-400">Avg CPU {item.average_cpu_percent}% · Peak {item.peak_cpu_percent}%</p><p className="text-xs text-slate-400">Avg memory {item.average_memory_percent}% · Peak {item.peak_memory_percent}%</p><p className="mt-3 text-xs leading-5 text-slate-500">{item.reason}</p><p className="mt-2 text-[10px] font-bold uppercase tracking-wider text-cyan-300">{item.recommended_action.replaceAll("_", " ")}</p><p className="mt-2 text-[10px] text-slate-600">{item.sample_count} samples</p></div>)}</div> : <p className="text-sm text-slate-500">No recommendations yet. Additional metric history is needed.</p>}
              </Panel>
            </div>
          )}

          {tab === "settings" && (
            <div className="grid gap-5 xl:grid-cols-[1fr_1.1fr]">
              <Panel>
                <SectionTitle eyebrow="Alert policy" title="Resource thresholds" description="Warning and critical limits are applied to new metric collections." />
                <form onSubmit={saveThresholds} className="space-y-4">
                  <div className="grid grid-cols-[1fr_1fr_1fr] gap-2 text-[10px] font-bold uppercase tracking-wider text-slate-500"><span>Metric</span><span>Warning %</span><span>Critical %</span></div>
                  {(["cpu", "memory", "disk"] as (keyof Thresholds)[]).map((metric) => <div key={metric} className="grid grid-cols-[1fr_1fr_1fr] items-center gap-2"><span className="text-sm font-medium capitalize text-slate-200">{metric}</span><input type="number" min="1" max="99" step="0.5" value={thresholds[metric].warning} onChange={(event) => updateThreshold(metric, "warning", event.target.value)} className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400" /><input type="number" min="2" max="100" step="0.5" value={thresholds[metric].critical} onChange={(event) => updateThreshold(metric, "critical", event.target.value)} className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400" /></div>)}
                  <button disabled={busy || user?.role !== "admin"} className="w-full rounded-xl bg-cyan-400 px-4 py-3 text-xs font-bold text-slate-950 disabled:cursor-not-allowed disabled:opacity-40">Save threshold policy</button>
                  {user?.role !== "admin" && <p className="text-[10px] text-slate-600">Administrator sign-in required to modify alert policy.</p>}
                  {thresholdSaved && <p className="text-xs text-emerald-300">{thresholdSaved}</p>}
                </form>
              </Panel>
              <Panel>
                <SectionTitle eyebrow="Outbound delivery" title="Notification activity" description="Delivery attempts are logged for SNS, email and Slack, including skipped/unconfigured channels." />
                {notifications.length ? <div className="space-y-2">{notifications.map((notification) => <div key={notification.id} className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-800 bg-slate-950/60 p-3"><div className="grid h-8 w-8 place-items-center rounded-lg bg-slate-800 text-xs font-bold uppercase text-slate-300">{notification.channel.slice(0, 2)}</div><div className="min-w-0 flex-1"><p className="text-xs font-semibold capitalize text-slate-200">{notification.channel} · incident {notification.incident_id ?? "—"}</p><p className="mt-1 text-[10px] text-slate-500">{notification.instance_id ?? "unknown instance"} · {new Date(notification.created_at).toLocaleString()}</p></div><Pill tone={notification.status === "sent" ? "green" : notification.status === "failed" ? "red" : "slate"}>{notification.status}</Pill></div>)}</div> : <p className="text-sm text-slate-500">No notification attempts have been recorded yet.</p>}
                <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/50 p-4"><p className="text-xs font-semibold text-slate-300">Provider configuration</p><p className="mt-2 text-xs leading-5 text-slate-500">Set SMTP variables for email, SLACK_WEBHOOK_URL for Slack, and CLOUDPULSE_SNS_TOPIC_ARN for SNS in the backend environment. Secrets are never returned to this dashboard.</p></div>
              </Panel>
            </div>
          )}

          <footer className="mt-8 flex flex-col justify-between gap-2 border-t border-slate-800/80 pt-4 text-[10px] text-slate-600 sm:flex-row"><span>CloudPulse Sentinel · Intelligent cloud operations</span><span>Data refresh: {lastRefresh ? new Date(lastRefresh).toLocaleTimeString() : "waiting"} · {refreshRate ? `${refreshRate / 1000}s polling` : "manual polling"}</span></footer>
        </section>
      </div>
    </main>
  );
}
