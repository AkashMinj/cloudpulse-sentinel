
"use client";

import { useEffect, useState } from "react";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

type DashboardData = {
  instance_id: string;
  latest_metrics: {
    cpu_usage_percent: number;
    memory_usage_percent: number;
    disk_usage_percent: number;
    timestamp: string;
  };
  incidents: {
    open: number;
    total: number;
  };
};

type Metric = {
  timestamp: string;
  cpu_usage_percent: number;
  memory_usage_percent: number;
  disk_usage_percent: number;
};

type MetricsResponse = {
  count: number;
  metrics: Metric[];
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
  created_at: string;
};

type IncidentsResponse = {
  count: number;
  incidents: Incident[];
};

export default function Home() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [history, setHistory] = useState<Metric[]>([]);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [error, setError] = useState("");

  async function fetchDashboard() {
    try {
      const response = await fetch(
        "/api/backend/v1/dashboard/summary",
        { cache: "no-store" }
      );

      if (!response.ok) {
        throw new Error("Failed to fetch dashboard data");
      }

      const result: DashboardData = await response.json();

      setData(result);
      setError("");
    } catch (err) {
      setError("Unable to connect to the backend");
      console.error("Dashboard error:", err);
    }
  }

  async function fetchHistory() {
    try {
      const response = await fetch(
        "/api/backend/v1/metrics/history?limit=20",
        { cache: "no-store" }
      );

      if (!response.ok) {
        throw new Error("Failed to fetch metrics history");
      }

      const result: MetricsResponse = await response.json();

      setHistory(result.metrics);
    } catch (err) {
      console.error("History error:", err);
    }
  }

  async function fetchIncidents() {
    try {
      const response = await fetch(
        "/api/backend/v1/incidents",
        { cache: "no-store" }
      );

      if (!response.ok) {
        throw new Error("Failed to fetch incidents");
      }

      const result: IncidentsResponse = await response.json();

      setIncidents(result.incidents);
    } catch (err) {
      console.error("Incidents error:", err);
    }
  }

  useEffect(() => {
    fetchDashboard();
    fetchHistory();
    fetchIncidents();

    const interval = setInterval(() => {
      fetchDashboard();
      fetchHistory();
      fetchIncidents();
    }, 30000);

    return () => clearInterval(interval);
  }, []);

  const chartData = history.map((metric) => ({
    time: new Date(metric.timestamp).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    }),
    cpu: metric.cpu_usage_percent,
    memory: metric.memory_usage_percent,
    disk: metric.disk_usage_percent,
  }));

  const getSeverityStyle = (severity: string) => {
    if (severity.toLowerCase() === "critical") {
      return "bg-red-950 text-red-400";
    }

    return "bg-yellow-950 text-yellow-400";
  };

  const getStatusStyle = (status: string) => {
    if (status.toLowerCase() === "resolved") {
      return "bg-green-950 text-green-400";
    }

    return "bg-orange-950 text-orange-400";
  };

  return (
    <main className="min-h-screen bg-slate-950 p-4 text-white sm:p-8">
      <div className="mx-auto max-w-7xl">

        {/* Header */}
        <div className="mb-8">
          <p className="text-sm font-semibold tracking-wider text-cyan-400">
            CLOUDPULSE SENTINEL
          </p>

          <h1 className="mt-2 text-3xl font-bold sm:text-4xl">
            Cloud Operations Dashboard
          </h1>

          <p className="mt-2 text-slate-400">
            Monitor your AWS infrastructure in real time.
          </p>
        </div>

        {/* Error */}
        {error && (
          <div className="mb-6 rounded-xl border border-red-800 bg-red-950 p-4 text-red-300">
            {error}
          </div>
        )}

        {/* Instance Information */}
        <div className="mb-6 rounded-xl border border-slate-800 bg-slate-900 p-5">
          <p className="text-sm text-slate-400">
            EC2 Instance
          </p>

          <h2 className="mt-2 break-all font-mono text-lg">
            {data?.instance_id || "Loading..."}
          </h2>

          <p className="mt-2 text-sm text-green-400">
            ● Connected to backend
          </p>
        </div>

        {/* Resource Cards */}
        <div className="grid gap-6 md:grid-cols-3">

          <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
            <p className="text-sm text-slate-400">
              CPU Usage
            </p>

            <h2 className="mt-3 text-4xl font-bold text-cyan-400">
              {data
                ? `${data.latest_metrics.cpu_usage_percent}%`
                : "--"}
            </h2>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
            <p className="text-sm text-slate-400">
              Memory Usage
            </p>

            <h2 className="mt-3 text-4xl font-bold text-green-400">
              {data
                ? `${data.latest_metrics.memory_usage_percent}%`
                : "--"}
            </h2>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
            <p className="text-sm text-slate-400">
              Disk Usage
            </p>

            <h2 className="mt-3 text-4xl font-bold text-purple-400">
              {data
                ? `${data.latest_metrics.disk_usage_percent}%`
                : "--"}
            </h2>
          </div>

        </div>

        {/* Incident Summary Cards */}
        <div className="mt-6 grid gap-6 md:grid-cols-2">

          <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
            <p className="text-sm text-slate-400">
              Open Incidents
            </p>

            <h2 className="mt-3 text-4xl font-bold text-yellow-400">
              {data ? data.incidents.open : "--"}
            </h2>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
            <p className="text-sm text-slate-400">
              Total Incidents
            </p>

            <h2 className="mt-3 text-4xl font-bold text-orange-400">
              {data ? data.incidents.total : "--"}
            </h2>
          </div>

        </div>

        {/* Resource Usage Chart */}
        <div className="mt-6 rounded-xl border border-slate-800 bg-slate-900 p-6">

          <h2 className="mb-6 text-xl font-semibold">
            Resource Usage History
          </h2>

          <div className="h-80 w-full">

            {chartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData}>

                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="#334155"
                  />

                  <XAxis
                    dataKey="time"
                    stroke="#94a3b8"
                  />

                  <YAxis
                    domain={[0, 100]}
                    stroke="#94a3b8"
                  />

                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#0f172a",
                      border: "1px solid #334155",
                      borderRadius: "8px",
                      color: "#ffffff",
                    }}
                  />

                  <Legend />

                  <Line
                    type="monotone"
                    dataKey="cpu"
                    name="CPU %"
                    stroke="#22d3ee"
                    strokeWidth={2}
                    dot={false}
                  />

                  <Line
                    type="monotone"
                    dataKey="memory"
                    name="Memory %"
                    stroke="#4ade80"
                    strokeWidth={2}
                    dot={false}
                  />

                  <Line
                    type="monotone"
                    dataKey="disk"
                    name="Disk %"
                    stroke="#c084fc"
                    strokeWidth={2}
                    dot={false}
                  />

                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-slate-400">
                Loading metrics history...
              </div>
            )}

          </div>
        </div>

        {/* Incident Dashboard */}
        <div className="mt-6 rounded-xl border border-slate-800 bg-slate-900 p-6">

          <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-xl font-semibold">
              Incident Dashboard
            </h2>

            <span className="rounded-full bg-slate-800 px-3 py-1 text-sm text-slate-300">
              {incidents.length} incidents
            </span>
          </div>

          {incidents.length === 0 ? (
            <p className="text-slate-400">
              No incidents detected.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[850px] text-left text-sm">

                <thead className="border-b border-slate-700 text-slate-400">
                  <tr>
                    <th className="px-4 py-3">Incident</th>
                    <th className="px-4 py-3">Severity</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Value</th>
                    <th className="px-4 py-3">Detected</th>
                  </tr>
                </thead>

                <tbody>
                  {incidents.map((incident) => (
                    <tr
                      key={incident.id}
                      className="border-b border-slate-800"
                    >

                      <td className="px-4 py-4">
                        <p className="font-semibold text-white">
                          {incident.title}
                        </p>

                        <p className="mt-1 max-w-md text-xs text-slate-400">
                          {incident.description}
                        </p>

                        <p className="mt-1 text-xs text-slate-500">
                          {incident.incident_type}
                        </p>
                      </td>

                      <td className="px-4 py-4">
                        <span
                          className={`rounded-full px-3 py-1 text-xs font-semibold ${getSeverityStyle(
                            incident.severity
                          )}`}
                        >
                          {incident.severity.toUpperCase()}
                        </span>
                      </td>

                      <td className="px-4 py-4">
                        <span
                          className={`rounded-full px-3 py-1 text-xs font-semibold ${getStatusStyle(
                            incident.status
                          )}`}
                        >
                          {incident.status.toUpperCase()}
                        </span>
                      </td>

                      <td className="px-4 py-4 text-slate-300">
                        {incident.metric_value}%

                        <span className="text-xs text-slate-500">
                          {" "}
                          / {incident.threshold_value}%
                        </span>
                      </td>

                      <td className="whitespace-nowrap px-4 py-4 text-slate-400">
                        {new Date(
                          incident.detected_at
                        ).toLocaleString()}
                      </td>

                    </tr>
                  ))}
                </tbody>

              </table>
            </div>
          )}

        </div>

        {/* Last Metrics Update */}
        <div className="mt-6 rounded-xl border border-slate-800 bg-slate-900 p-6">

          <h2 className="text-lg font-semibold">
            Last Metrics Update
          </h2>

          <p className="mt-3 text-slate-400">
            {data
              ? new Date(
                  data.latest_metrics.timestamp
                ).toLocaleString()
              : "Loading..."}
          </p>

        </div>

      </div>
    </main>
  );
}
