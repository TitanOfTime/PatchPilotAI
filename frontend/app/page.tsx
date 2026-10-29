"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import {
  Activity,
  ArrowDownLeft,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Circle,
  Code2,
  Command,
  ExternalLink,
  FileCode2,
  FlaskConical,
  FolderGit2,
  GitBranch,
  GitPullRequest,
  LayoutDashboard,
  Loader2,
  MessageSquare,
  Moon,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Sun,
  Terminal,
  X,
  Zap,
} from "lucide-react";
import {
  api,
  type Evaluation,
  type Health,
  type Metrics,
  type Repository,
  type Run,
  type SearchResult,
} from "@/lib/api";

import { StatusLabel, EvidenceCards } from "@/components/evidence";

const navigation = [
  { name: "Overview", icon: LayoutDashboard, group: "workspace" },
  { name: "Repositories", icon: FolderGit2, group: "workspace" },
  { name: "Code intelligence", icon: MessageSquare, group: "workspace" },
  { name: "Agent workspace", icon: Command, group: "workspace" },
  { name: "Evaluations", icon: Activity, group: "observe" },
  { name: "Settings", icon: Settings2, group: "observe" },
];
const stages = ["fetch", "retrieve", "diagnose", "patch", "review", "test"];
export default function Dashboard() {
  const [view, setView] = useState("Overview");
  const [repos, setRepos] = useState<Repository[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  const [url, setUrl] = useState(
    "https://github.com/TitanOfTime/TestBankingApp",
  );
  const [query, setQuery] = useState("");
  const [answerMode, setAnswerMode] = useState<"ask" | "search">("ask");
  const [result, setResult] = useState<SearchResult | null>(null);
  const [issue, setIssue] = useState("");
  const [issueNumber, setIssueNumber] = useState("");
  const [issueData, setIssueData] = useState<unknown>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [modelList, setModelList] = useState<string[]>([]);
  const [mcpResult, setMcpResult] = useState<unknown>(null);
  const [dark, setDark] = useState(false);
  const [approval, setApproval] = useState<"review" | "test" | "draft_pr">(
    "review",
  );
  const dialog = useRef<HTMLDialogElement>(null);
  const repo = repos.find((r) => r.id === selected);

  const reload = useCallback(async () => {
    const [h, r, m, a, e] = await Promise.allSettled([
      api<Health>("/health"),
      api<Repository[]>("/repositories"),
      api<Metrics>("/metrics"),
      api<Run[]>("/agents/runs"),
      api<Evaluation | null>("/evaluations/latest"),
    ]);
    if (h.status === "fulfilled") setHealth(h.value);
    if (r.status === "fulfilled") {
      setRepos(r.value);
      setSelected(
        (old) =>
          old ||
          r.value.find((r) => !r.meta.fixture)?.id ||
          r.value[0]?.id ||
          "",
      );
    }
    if (m.status === "fulfilled") setMetrics(m.value);
    if (a.status === "fulfilled") setRuns(a.value);
    if (e.status === "fulfilled") setEvaluation(e.value);
    if (h.status === "rejected")
      setLoadError(
        "Backend is offline. Start the FastAPI server on port 8000.",
      );
    else if (r.status === "rejected") setLoadError(r.reason.message);
    else setLoadError("");
  }, []);
  useEffect(() => {
    const initial = setTimeout(() => void reload(), 0);
    const timer = setInterval(() => void reload(), 7000);
    return () => {
      clearTimeout(initial);
      clearInterval(timer);
    };
  }, [reload]);
  useEffect(() => {
    if (!run || !["running", "resuming"].includes(run.status)) return;
    const timer = setInterval(() => {
      api<Run>("/agents/runs/" + run.id)
        .then(setRun)
        .catch((e) => setError(e.message));
    }, 1800);
    return () => clearInterval(timer);
  }, [run]);

  async function perform(name: string, fn: () => Promise<void>) {
    setBusy(name);
    setError("");
    setNotice("");
    try {
      await fn();
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy("");
    }
  }
  function go(name: string) {
    setView(name);
    setError("");
    setNotice("");
  }
  async function connect(event: FormEvent) {
    event.preventDefault();
    await perform("connect", async () => {
      const r = await api<Repository>("/repositories", { url });
      setSelected(r.id);
      await api("/repositories/" + r.id + "/index", {});
      setNotice(
        "Repository connected. Indexing is running; progress updates automatically.",
      );
    });
  }
  async function question(event: FormEvent) {
    event.preventDefault();
    if (!selected) return;
    await perform("query", async () => {
      setResult(
        await api<SearchResult>("/retrieval/" + answerMode, {
          repository_id: selected,
          query,
        }),
      );
    });
  }
  async function investigate(event: FormEvent) {
    event.preventDefault();
    await perform("agent", async () => {
      const created = await api<{ id: string }>("/agents/runs", {
        repository_id: selected,
        issue,
        issue_number: issueNumber ? Number(issueNumber) : null,
      });
      setRun(await api<Run>("/agents/runs/" + created.id));
    });
  }
  async function approveAction() {
    if (!run) return;
    dialog.current?.close();
    await perform("approval", async () => {
      const profile = repo?.meta.fixture ? "fixture_python" : "banking_maven";
      const gate = await api<{ approval_id: string }>(
        "/agents/runs/" + run.id + "/approve",
        { action: approval, profile: approval === "test" ? profile : null },
      );
      if (approval === "test")
        await api("/tests/run", {
          run_id: run.id,
          approval_id: gate.approval_id,
          profile,
        });
      if (approval === "draft_pr") {
        const pr = await api<{ url: string }>("/pull-requests/draft", {
          run_id: run.id,
          approval_id: gate.approval_id,
        });
        setNotice("Draft pull request created: " + pr.url);
      }
      setRun(await api<Run>("/agents/runs/" + run.id));
    });
  }
  function review(action: "review" | "test" | "draft_pr") {
    setApproval(action);
    dialog.current?.showModal();
  }
  function selectRun(item: Run) {
    setSelected(item.repository_id);
    go("Agent workspace");
    void perform("load-run", async () =>
      setRun(await api<Run>("/agents/runs/" + item.id)),
    );
  }
  const ready = repos.filter((r) => r.status === "ready");

  return (
    <div className={"app-shell " + (dark ? "dark" : "")}>
      <aside className="sidebar">
        <button
          className="brand"
          aria-label="PatchPilot overview"
          onClick={() => go("Overview")}
        >
          <span className="brand-mark">
            <Sparkles size={21} strokeWidth={2} />
          </span>
          <span>
            PatchPilot<span className="brand-ai">AI</span>
          </span>
        </button>
        <div className="workspace-label">
          Personal workspace <ChevronDown size={12} />
        </div>
        <nav aria-label="Main navigation">
          {navigation.map((item, i) => (
            <div key={item.name}>
              {i === 4 && (
                <div className="nav-section">Insights & controls</div>
              )}
              <button
                className={"nav-item " + (view === item.name ? "active" : "")}
                aria-label={item.name}
                title={item.name}
                onClick={() => go(item.name)}
              >
                <item.icon size={18} />
                <span>{item.name}</span>
                {item.name === "Repositories" && (
                  <span className="nav-count">{repos.length}</span>
                )}
                {item.name === "Agent workspace" && (
                  <span className="nav-new">AGENT</span>
                )}
              </button>
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="local-card">
            <div className="local-title">
              <ShieldCheck size={17} />
              <strong>Your code. Your control.</strong>
            </div>
            <p>
              Local embeddings. Traceable fixes.
              <br />A human has the final say.
            </p>
            <button onClick={() => go("Settings")}>
              View configuration <ArrowUpRight size={13} />
            </button>
          </div>
          <button className="profile" onClick={() => go("Settings")}>
            <span className="avatar">P</span>
            <span>
              <strong>Local workspace</strong>
              <small>Personal environment</small>
            </span>
            <Settings2 size={15} />
          </button>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <ChevronRight size={13} />
            <strong>{view}</strong>
          </div>
          <div className="topbar-actions">
            <span className="connection">
              {health?.database === "connected" ? (
                <ShieldCheck size={14} aria-hidden="true" />
              ) : (
                <Activity size={14} aria-hidden="true" />
              )}
              {health?.database === "connected"
                ? "Local environment connected"
                : "Environment needs attention"}
            </span>
            <button
              className="icon-button"
              aria-label="Toggle color theme"
              onClick={() => setDark(!dark)}
            >
              {dark ? <Sun size={17} /> : <Moon size={17} />}
            </button>
            <span className="avatar small">P</span>
          </div>
        </header>
        <main>
          {(error || loadError) && (
            <div className="alert error" role="alert">
              <X size={17} />
              <span>{error || loadError}</span>
              <button
                aria-label="Dismiss error"
                onClick={() => {
                  setError("");
                  setLoadError("");
                }}
              >
                <X size={15} />
              </button>
            </div>
          )}
          {notice && (
            <div className="alert success" role="status">
              <CheckCircle2 size={17} />
              <span>{notice}</span>
              <button
                aria-label="Dismiss notification"
                onClick={() => setNotice("")}
              >
                <X size={15} />
              </button>
            </div>
          )}
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                {view === "Overview"
                  ? "Repository intelligence"
                  : "Your workspace"}
              </div>
              <h1>
                {view === "Overview" ? "A clear path from issue to fix." : view}
              </h1>
              <p>
                {
                  (
                    {
                      Overview:
                        "Understand your codebase. Investigate with evidence. Ship with confidence.",
                      Repositories:
                        "Bring your source code into focus with local, revision-aware indexing.",
                      "Code intelligence":
                        "Ask better questions. Get answers grounded in your actual source code.",
                      "Agent workspace":
                        "From a reported symptom to a patch you can inspect and approve.",
                      Evaluations:
                        "Measure retrieval quality and inspect real execution outcomes.",
                      Settings:
                        "A transparent view of your local environment and connected services.",
                    } as Record<string, string>
                  )[view]
                }
              </p>
            </div>
            {view === "Overview" && (
              <button className="primary" onClick={() => go("Repositories")}>
                <Plus size={16} />
                Connect repository
              </button>
            )}
          </div>

          {view === "Overview" && (
            <>
              <section className="stats-grid" aria-label="Workspace statistics">
                {[
                  {
                    label: "Connected repositories",
                    value: repos.length,
                    note: `${ready.length} ready for retrieval`,
                    icon: FolderGit2,
                  },
                  {
                    label: "Indexed source chunks",
                    value: repos.reduce((n, r) => n + r.chunks, 0),
                    note: "Embedded locally with PyTorch",
                    icon: Code2,
                  },
                  {
                    label: "Agent investigations",
                    value: runs.length,
                    note: `${runs.filter((r) => r.status === "awaiting_review").length} awaiting your review`,
                    icon: Command,
                  },
                  {
                    label: "Gemini requests today",
                    value: metrics?.gemini_requests_today ?? 0,
                    note: `Of ${metrics?.gemini_daily_budget ?? "—"} configured daily requests`,
                    icon: Zap,
                  },
                ].map((stat) => (
                  <article className="stat-card" key={stat.label}>
                    <div>
                      <span>{stat.label}</span>
                      <stat.icon size={17} />
                    </div>
                    <strong>{stat.value.toLocaleString()}</strong>
                    <small>{stat.note}</small>
                  </article>
                ))}
              </section>
              <section className="overview-split">
                <article className="start-card">
                  <div className="tag">
                    <Sparkles size={13} />
                    Source-grounded intelligence
                  </div>
                  <h2>
                    Your next fix starts
                    <br />
                    with understanding.
                  </h2>
                  <p>
                    Explore a repository, follow the evidence, and turn a bug
                    report into a reviewable change.
                  </p>
                  <button
                    className="primary"
                    onClick={() => go("Code intelligence")}
                  >
                    Ask your codebase <ArrowRight size={16} />
                  </button>
                  <div className="flow-mini">
                    <span>
                      <Search size={14} />
                      Retrieve
                    </span>
                    <ChevronRight size={12} />
                    <span>
                      <Command size={14} />
                      Investigate
                    </span>
                    <ChevronRight size={12} />
                    <span>
                      <ShieldCheck size={14} />
                      Review
                    </span>
                  </div>
                </article>
                <article className="panel repos-panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Your repositories</h2>
                      <p>Real source. Indexed at a pinned revision.</p>
                    </div>
                    <button
                      className="text-button"
                      onClick={() => go("Repositories")}
                    >
                      View all <ArrowUpRight size={14} />
                    </button>
                  </div>
                  {repos.length ? (
                    repos.slice(0, 3).map((r) => (
                      <button
                        className="repo-row"
                        key={r.id}
                        onClick={() => {
                          setSelected(r.id);
                          go("Repositories");
                        }}
                      >
                        <span className="repo-icon">
                          <FolderGit2 size={20} />
                        </span>
                        <span className="row-main">
                          <strong>{r.name.split("/").pop()}</strong>
                          <small>
                            {r.meta.fixture
                              ? "Demo fixture"
                              : r.name.split("/")[0]}{" "}
                            · {r.files} files · {r.chunks} chunks
                          </small>
                        </span>
                        <StatusLabel value={r.status} />
                      </button>
                    ))
                  ) : (
                    <div className="empty">
                      <FolderGit2 size={30} />
                      <h3>A workspace for your code</h3>
                      <p>
                        Connect your Banking App to index its source and start
                        exploring.
                      </p>
                      <button
                        className="secondary"
                        onClick={() => go("Repositories")}
                      >
                        Connect a repository <Plus size={14} />
                      </button>
                    </div>
                  )}
                  <div className="panel-footer">
                    <ShieldCheck size={14} />
                    Read-only ingestion. No repository code is executed.
                  </div>
                </article>
              </section>
              <section className="panel">
                <div className="panel-heading">
                  <div>
                    <h2>Recent investigations</h2>
                    <p>Every step, source, and proposed change in one place.</p>
                  </div>
                  <button
                    className="text-button"
                    onClick={() => go("Agent workspace")}
                  >
                    Open workspace <ArrowUpRight size={14} />
                  </button>
                </div>
                {runs.length ? (
                  <div className="run-table">
                    {runs.slice(0, 5).map((r) => (
                      <button
                        key={r.id}
                        className="run-row"
                        onClick={() => selectRun(r)}
                      >
                        <span className="activity-icon">
                          <GitPullRequest size={18} />
                        </span>
                        <span className="row-main">
                          <strong>{r.data.issue}</strong>
                          <small>
                            {
                              repos.find((repo) => repo.id === r.repository_id)
                                ?.name
                            }{" "}
                            ·{" "}
                            {r.data.origin === "integration_test"
                              ? "Integration test  /  fixed proposal  /  "
                              : ""}
                            {new Date(r.created_at).toLocaleString()}
                          </small>
                        </span>
                        <StatusLabel value={r.status} />
                        <ChevronRight size={15} />
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="empty horizontal">
                    <div className="activity-icon">
                      <Command size={23} />
                    </div>
                    <div>
                      <h3>No investigations yet</h3>
                      <p>
                        Give the agent a bug report. It will retrieve evidence
                        and propose a fix for your review.
                      </p>
                    </div>
                    <button
                      className="secondary"
                      onClick={() => go("Agent workspace")}
                    >
                      Start investigation <ArrowRight size={14} />
                    </button>
                  </div>
                )}
              </section>
              <div className="quiet-note">
                <ShieldCheck size={14} />
                Built around your approval. Tests and remote changes require
                separate permission.
              </div>
            </>
          )}

          {view === "Repositories" && (
            <>
              <section className="panel form-panel">
                <div className="section-icon">
                  <FolderGit2 size={22} />
                </div>
                <h2>Connect a GitHub repository</h2>
                <p>
                  Public repositories are cloned into an isolated local cache.
                  Source code stays tied to its commit.
                </p>
                <form onSubmit={connect} className="inline-form">
                  <label className="sr-only" htmlFor="repository-url">
                    GitHub repository URL
                  </label>
                  <input
                    id="repository-url"
                    type="url"
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    required
                    placeholder="https://github.com/owner/repository"
                  />
                  <button className="primary" disabled={!!busy}>
                    {busy === "connect" ? (
                      <Loader2 className="spin" size={16} />
                    ) : (
                      <Plus size={16} />
                    )}
                    Connect & index
                  </button>
                </form>
              </section>
              <div className="section-title">
                <h2>
                  Connected repositories <span>{repos.length}</span>
                </h2>
                <button className="text-button" onClick={() => void reload()}>
                  <RefreshCw size={14} />
                  Refresh
                </button>
              </div>
              <div className="repository-grid">
                {repos.map((r) => (
                  <article
                    className={
                      "panel repository-card " +
                      (selected === r.id ? "selected-card" : "")
                    }
                    key={r.id}
                  >
                    <div className="repo-card-top">
                      <span className="repo-icon">
                        <FolderGit2 size={24} />
                      </span>
                      <StatusLabel value={r.status} />
                    </div>
                    <h2>{r.name}</h2>
                    {r.meta.fixture && (
                      <span className="tag">DEMO FIXTURE · SEEDED DEFECT</span>
                    )}
                    <p className="mono">
                      {r.sha ? (
                        <>
                          <GitBranch size={13} />
                          {r.sha.slice(0, 12)}
                        </>
                      ) : (
                        "No indexed revision yet"
                      )}
                    </p>
                    <div className="repo-facts">
                      <span>
                        <strong>{r.files}</strong>source files
                      </span>
                      <span>
                        <strong>{r.chunks}</strong>code chunks
                      </span>
                      <span>
                        <strong>{r.meta.skipped ?? 0}</strong>filtered files
                      </span>
                    </div>
                    {r.error && <div className="inline-error">{r.error}</div>}
                    <div className="button-row">
                      <button
                        className="secondary"
                        onClick={() => {
                          setSelected(r.id);
                          go("Code intelligence");
                        }}
                        disabled={r.status !== "ready"}
                      >
                        Explore code <ArrowRight size={14} />
                      </button>
                      <button
                        className="icon-button"
                        aria-label={"Reindex " + r.name}
                        disabled={
                          !!busy ||
                          ["queued", "cloning", "embedding"].includes(r.status)
                        }
                        onClick={() =>
                          void perform("index", async () => {
                            await api("/repositories/" + r.id + "/index", {});
                            setNotice("Indexing queued.");
                          })
                        }
                      >
                        <RefreshCw size={16} />
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            </>
          )}

          {(view === "Code intelligence" ||
            view === "Agent workspace" ||
            view === "Evaluations") && (
            <div className="repo-selector">
              <FolderGit2 size={16} />
              <label className="sr-only" htmlFor="active-repository">
                Active repository
              </label>
              <select
                id="active-repository"
                value={selected}
                onChange={(e) => {
                  setSelected(e.target.value);
                  setResult(null);
                  setRun(null);
                }}
              >
                <option value="" disabled>
                  Select a repository
                </option>
                {repos.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                    {r.meta.fixture ? " · Demo fixture" : ""}
                  </option>
                ))}
              </select>
              {repo && (
                <>
                  <div className="repo-context">
                    <StatusLabel value={repo.status} />
                    {repo.sha && (
                      <span className="mono revision">
                        <GitBranch size={13} aria-hidden="true" />
                        {repo.sha.slice(0, 8)}
                      </span>
                    )}
                  </div>
                </>
              )}
            </div>
          )}

          {view === "Code intelligence" && (
            <div className="intelligence-layout">
              <section className="panel ask-panel">
                <div className="section-icon">
                  <MessageSquare size={22} />
                </div>
                <h2>What would you like to understand?</h2>
                <p>
                  Follow a request, find a service, or investigate how something
                  works.
                </p>
                <form onSubmit={question}>
                  <label className="sr-only" htmlFor="query">
                    Question about the repository
                  </label>
                  <textarea
                    id="query"
                    rows={4}
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    required
                    minLength={2}
                    placeholder="Where are payment webhooks and idempotency handled?"
                  />
                  <div className="form-toolbar">
                    <div className="segmented">
                      <button
                        type="button"
                        className={answerMode === "ask" ? "chosen" : ""}
                        onClick={() => setAnswerMode("ask")}
                      >
                        <Sparkles size={13} />
                        Grounded answer
                      </button>
                      <button
                        type="button"
                        className={answerMode === "search" ? "chosen" : ""}
                        onClick={() => setAnswerMode("search")}
                      >
                        <Search size={13} />
                        Search only
                      </button>
                    </div>
                    <button
                      className="primary"
                      disabled={!!busy || repo?.status !== "ready"}
                    >
                      {busy === "query" ? (
                        <Loader2 className="spin" size={16} />
                      ) : (
                        <ArrowRight size={16} />
                      )}
                      Ask repository
                    </button>
                  </div>
                </form>
                <div className="suggestions">
                  {[
                    "Where are payment webhooks and idempotency handled?",
                    "How are JWT tokens generated and validated?",
                    "How does the transfer saga compensate failures?",
                  ].map((q) => (
                    <button key={q} onClick={() => setQuery(q)}>
                      <ArrowDownLeft size={13} />
                      {q}
                    </button>
                  ))}
                </div>
              </section>
              {result ? (
                <section className="panel answer-panel">
                  <div className="panel-heading">
                    <h2>
                      {result.answer
                        ? "Source-grounded answer"
                        : "Retrieved evidence"}
                    </h2>
                    <span className="subtle">
                      {result.latency_ms} ms retrieval · {result.mode}
                    </span>
                  </div>
                  {result.answer && (
                    <div className="answer-text">
                      <StatusLabel
                        value={
                          result.insufficient_evidence
                            ? "insufficient evidence"
                            : "grounded in source"
                        }
                      />
                      <p>{result.answer}</p>
                    </div>
                  )}
                  <div className="evidence-title">
                    <BookOpen size={15} />
                    {result.evidence.length} source references
                  </div>
                  <EvidenceCards items={result.evidence} />
                </section>
              ) : (
                <div className="hint-card">
                  <BookOpen size={20} />
                  <div>
                    <h3>Answers with a paper trail</h3>
                    <p>
                      Hybrid search combines semantic similarity and PostgreSQL
                      full-text search. Every result includes its source lines
                      and indexed commit. Search-only mode uses no Gemini
                      requests.
                    </p>
                  </div>
                </div>
              )}
            </div>
          )}

          {view === "Agent workspace" && (
            <>
              <div className="agent-layout">
                <section className="panel issue-panel">
                  <h2>Start an investigation</h2>
                  <p>
                    Use a GitHub issue or a clearly labeled manual bug report.
                  </p>
                  <form onSubmit={investigate}>
                    <label htmlFor="issue-number">
                      GitHub issue number{" "}
                      <span className="subtle">(optional)</span>
                    </label>
                    <input
                      id="issue-number"
                      type="number"
                      min={1}
                      value={issueNumber}
                      onChange={(e) => setIssueNumber(e.target.value)}
                      placeholder="e.g. 12"
                    />
                    <label htmlFor="issue-description">
                      {issueNumber ? "Issue context" : "Manual bug report"}
                    </label>
                    <textarea
                      id="issue-description"
                      rows={6}
                      value={issue}
                      onChange={(e) => setIssue(e.target.value)}
                      required
                      minLength={8}
                      placeholder={
                        repo?.meta.fixture
                          ? 'cents("1.005") returns 100 instead of 101. Use ROUND_HALF_UP for positive and negative ties and add regression tests.'
                          : "Describe the symptom, expected behavior, and how to reproduce it…"
                      }
                    />
                    <button
                      className="primary full"
                      disabled={!!busy || repo?.status !== "ready"}
                    >
                      {busy === "agent" ? (
                        <Loader2 className="spin" size={16} />
                      ) : (
                        <Command size={16} />
                      )}
                      Investigate issue
                    </button>
                  </form>
                  <button
                    className="text-button issues-link"
                    disabled={!!busy || !selected}
                    onClick={() =>
                      void perform("issues", async () =>
                        setIssueData(
                          await api("/github/issues?repository_id=" + selected),
                        ),
                      )
                    }
                  >
                    Browse GitHub issues <ArrowUpRight size={14} />
                  </button>
                  {issueData !== null && (
                    <details>
                      <summary>GitHub MCP response</summary>
                      <pre className="tool-output">
                        {JSON.stringify(issueData, null, 2)}
                      </pre>
                    </details>
                  )}
                  <div className="runner-notice">
                    <ShieldCheck size={16} />
                    <p>
                      Investigations propose changes. Review, test execution,
                      and publishing are separate approvals.
                    </p>
                  </div>
                </section>
                <section className="panel investigation-panel">
                  <div className="panel-heading">
                    <h2>Investigation workspace</h2>
                    {run && <StatusLabel value={run.status} />}
                  </div>
                  {run ? (
                    <>
                      <div className="timeline">
                        {stages.map((stage, i) => {
                          const done =
                            run.steps?.some((s) => s.data.stage === stage) ||
                            (stage === "test" && !!run.test);
                          const active =
                            run.data.stage === stage &&
                            run.status === "running";
                          return (
                            <div
                              key={stage}
                              className={
                                done ? "done" : active ? "current" : ""
                              }
                            >
                              <span>
                                {done ? (
                                  <Check size={13} />
                                ) : active ? (
                                  <Loader2 size={13} className="spin" />
                                ) : (
                                  i + 1
                                )}
                              </span>
                              <small>{stage}</small>
                            </div>
                          );
                        })}
                      </div>
                      <div className="investigation-body">
                        <h3>{run.data.issue}</h3>
                        <p className="subtle mono">
                          Run {run.id.slice(0, 8)} ·{" "}
                          {repo?.meta.fixture
                            ? run.data.origin === "integration_test"
                              ? "Demo fixture  /  fixed integration-test proposal"
                              : "Demo fixture  /  Gemini proposal"
                            : run.data.issue_number
                              ? "GitHub issue"
                              : "Manual bug report"}
                        </p>
                        {run.data.error && (
                          <div className="alert error" role="alert">
                            {run.data.error}
                          </div>
                        )}
                        {run.data.proposal && (
                          <>
                            <h4>
                              Diagnosis{" "}
                              <span className="tag">
                                {run.data.proposal.confidence}
                              </span>
                            </h4>
                            <p>{run.data.proposal.diagnosis}</p>
                            <h4>Proposed plan</h4>
                            <ol className="plan">
                              {run.data.proposal.plan.map((p, i) => (
                                <li key={i}>{p}</li>
                              ))}
                            </ol>
                            <p className="subtle">
                              Regression strategy: {run.data.proposal.test_plan}
                            </p>
                            {run.data.proposal.limitations.map((l, i) => (
                              <p className="inline-warning" key={i}>
                                {l}
                              </p>
                            ))}
                          </>
                        )}
                        {run.data.patch && (
                          <>
                            <div className="diff-heading">
                              <h4>Proposed changes</h4>
                              <StatusLabel value="validated" />
                            </div>
                            <p className="subtle">
                              {run.data.patch.validation} · base{" "}
                              {run.data.patch.sha.slice(0, 8)}
                            </p>
                            <pre className="diff">
                              {run.data.patch.diff.split("\n").map((l, i) => (
                                <span
                                  className={
                                    l.startsWith("+")
                                      ? "added"
                                      : l.startsWith("-")
                                        ? "removed"
                                        : l.startsWith("@@")
                                          ? "hunk"
                                          : ""
                                  }
                                  key={i}
                                >
                                  {l}
                                  {"\n"}
                                </span>
                              ))}
                            </pre>
                          </>
                        )}
                        {run.status === "running" && (
                          <button
                            className="secondary"
                            disabled={!!busy}
                            onClick={() =>
                              void perform("cancel", async () => {
                                await api(
                                  "/agents/runs/" + run.id + "/cancel",
                                  {},
                                );
                                setRun(
                                  await api<Run>("/agents/runs/" + run.id),
                                );
                              })
                            }
                          >
                            Cancel investigation
                          </button>
                        )}
                        {run.status === "awaiting_review" && (
                          <div className="approval-bar">
                            <div>
                              <ShieldCheck size={20} />
                              <span>
                                <strong>Ready for your review</strong>
                                <small>
                                  Inspect the patch before approving.
                                </small>
                              </span>
                            </div>
                            <button
                              className="secondary"
                              disabled={!!busy}
                              onClick={() =>
                                void perform("reject", async () => {
                                  await api(
                                    "/agents/runs/" + run.id + "/reject",
                                    {},
                                  );
                                  setRun(
                                    await api<Run>("/agents/runs/" + run.id),
                                  );
                                })
                              }
                            >
                              Reject
                            </button>
                            <button
                              className="primary"
                              disabled={!!busy}
                              onClick={() => review("review")}
                            >
                              Approve patch <Check size={14} />
                            </button>
                          </div>
                        )}
                        {run.status === "approved" && (
                          <div className="approval-bar">
                            <p>
                              Patch approved. Run the reviewed test profile in a
                              disposable clone.
                            </p>
                            <button
                              className="primary"
                              disabled={
                                !!busy || !health?.local_test_execution_enabled
                              }
                              onClick={() => review("test")}
                            >
                              <FlaskConical size={15} />
                              Approve & run tests
                            </button>
                            {!health?.local_test_execution_enabled && (
                              <small>
                                Enable LOCAL_TEST_EXECUTION_ENABLED in .env
                                first.
                              </small>
                            )}
                          </div>
                        )}
                        {run.test && (
                          <div className="test-output">
                            <h4>
                              <Terminal size={16} />
                              Actual test output{" "}
                              <StatusLabel value={run.test.status} />
                            </h4>
                            <p className="subtle mono">
                              exit {run.test.data.exit_code} ·{" "}
                              {run.test.data.duration_ms} ms
                            </p>
                            <pre>
                              {run.test.data.stdout}
                              {run.test.data.stderr}
                            </pre>
                          </div>
                        )}
                        {run.status === "test_passed" && (
                          <button
                            className="primary"
                            disabled={
                              !!busy ||
                              !health?.github_remote_write_enabled ||
                              repo?.meta.fixture
                            }
                            onClick={() => review("draft_pr")}
                          >
                            <GitPullRequest size={15} />
                            Approve draft pull request
                          </button>
                        )}
                        {run.data.pr_url && (
                          <a
                            href={run.data.pr_url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            View draft pull request <ExternalLink size={14} />
                          </a>
                        )}
                        {run.data.evidence && (
                          <>
                            <h4>Source evidence</h4>
                            <EvidenceCards items={run.data.evidence} />
                          </>
                        )}
                        <details className="trace-details">
                          <summary>Execution traces & tool calls</summary>
                          <pre className="tool-output">
                            {JSON.stringify(
                              { steps: run.steps, tools: run.data.tools },
                              null,
                              2,
                            )}
                          </pre>
                        </details>
                      </div>
                    </>
                  ) : (
                    <div className="empty large">
                      <div className="agent-orbit">
                        <Command size={32} />
                        <span>
                          <Search size={14} />
                        </span>
                        <span>
                          <FileCode2 size={14} />
                        </span>
                      </div>
                      <h3>Every fix has a story.</h3>
                      <p>
                        Start an investigation to follow the agent from source
                        evidence to diagnosis, proposed changes, and human
                        review.
                      </p>
                      <span className="tag">POWERED BY LANGGRAPH + GEMINI</span>
                    </div>
                  )}
                </section>
              </div>
              {runs.length > 0 && (
                <section className="panel previous-runs">
                  <div className="panel-heading">
                    <h2>Investigation history</h2>
                  </div>
                  {runs.map((r) => (
                    <button
                      className="run-row"
                      key={r.id}
                      onClick={() => selectRun(r)}
                    >
                      <GitPullRequest size={17} />
                      <span className="row-main">
                        <strong>{r.data.issue}</strong>
                        <small>
                          {r.data.origin === "integration_test"
                            ? "Integration test  /  fixed proposal  /  "
                            : ""}
                          {new Date(r.created_at).toLocaleString()}
                        </small>
                      </span>
                      <StatusLabel value={r.status} />
                      <ChevronRight size={14} />
                    </button>
                  ))}
                </section>
              )}
            </>
          )}

          {view === "Evaluations" && (
            <>
              <section className="panel evaluation-intro">
                <div className="section-icon">
                  <Activity size={22} />
                </div>
                <div>
                  <h2>Retrieval quality, measured.</h2>
                  <p>
                    Compare vector, keyword, and hybrid retrieval against 10
                    hand-labeled Banking App queries. No Gemini requests.
                  </p>
                </div>
                <button
                  className="primary"
                  disabled={
                    !!busy || repo?.status !== "ready" || repo?.meta.fixture
                  }
                  onClick={() =>
                    void perform("evaluation", async () => {
                      const data = await api<
                        Evaluation["data"] & { id: string }
                      >("/evaluations/run", { repository_id: selected });
                      setEvaluation({ id: data.id, data });
                    })
                  }
                >
                  {busy === "evaluation" ? (
                    <Loader2 size={16} className="spin" />
                  ) : (
                    <FlaskConical size={16} />
                  )}
                  Run evaluation
                </button>
              </section>
              {evaluation ? (
                <>
                  <div className="evaluation-cards">
                    {Object.entries(evaluation.data.results).map(
                      ([mode, r]) => (
                        <article className="panel eval-card" key={mode}>
                          <div className="eval-mode">
                            {mode}
                            {mode === "hybrid" && (
                              <span className="tag">RRF FUSION</span>
                            )}
                          </div>
                          <div className="eval-numbers">
                            <div>
                              <strong>
                                {(r.recall_at_5 * 100).toFixed(0)}
                                <small>%</small>
                              </strong>
                              <span>Recall@5</span>
                            </div>
                            <div>
                              <strong>{r.mrr.toFixed(3)}</strong>
                              <span>MRR</span>
                            </div>
                          </div>
                          <div className="metric-track">
                            <span
                              style={{ width: `${r.recall_at_5 * 100}%` }}
                            />
                          </div>
                        </article>
                      ),
                    )}
                  </div>
                  <section className="panel">
                    <div className="panel-heading">
                      <div>
                        <h2>Query-level results</h2>
                        <p>
                          Hybrid retrieval · {evaluation.data.cases} questions ·{" "}
                          {new Date(evaluation.data.timestamp).toLocaleString()}
                        </p>
                      </div>
                    </div>
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>Question</th>
                            <th>Relevant in top 5</th>
                            <th>Reciprocal rank</th>
                            <th>Citations</th>
                            <th>Retrieval</th>
                          </tr>
                        </thead>
                        <tbody>
                          {evaluation.data.results.hybrid.cases.map((c, i) => (
                            <tr key={i}>
                              <td>{c.query}</td>
                              <td>{c.hit_at_5 ? "Yes" : "No"}</td>
                              <td>{c.reciprocal_rank.toFixed(3)}</td>
                              <td>
                                {c.citation_validity ? "Verified" : "Invalid"}
                              </td>
                              <td>{c.latency_ms} ms</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <div className="methodology">
                      {evaluation.data.methodology}
                    </div>
                  </section>
                </>
              ) : (
                <div className="panel empty large">
                  <FlaskConical size={32} />
                  <h3>Evidence before claims.</h3>
                  <p>
                    Run the benchmark on the indexed Banking App to see actual
                    retrieval measurements.
                  </p>
                </div>
              )}
              <section className="panel outcomes">
                <div className="panel-heading">
                  <h2>Recorded agent outcomes</h2>
                </div>
                <div className="outcome-grid">
                  {Object.entries(metrics?.agent_outcomes ?? {}).map(
                    ([status, count]) => (
                      <div key={status}>
                        <StatusLabel value={status} />
                        <strong>{count}</strong>
                      </div>
                    ),
                  )}
                  {!Object.keys(metrics?.agent_outcomes ?? {}).length && (
                    <p className="subtle">No agent runs recorded yet.</p>
                  )}
                </div>
              </section>
            </>
          )}

          {view === "Settings" && (
            <>
              <section className="panel">
                <div className="panel-heading">
                  <div>
                    <h2>Environment diagnostics</h2>
                    <p>
                      Connection state reflects real local services. Secrets are
                      never returned.
                    </p>
                  </div>
                  <button className="secondary" onClick={() => void reload()}>
                    <RefreshCw size={14} />
                    Refresh
                  </button>
                </div>
                <div className="settings-rows">
                  {[
                    {
                      icon: Activity,
                      name: "FastAPI backend",
                      detail: `Loopback · port 8000 · v${health?.version ?? "—"}`,
                      ready: health?.backend === "ok",
                      state: health?.backend === "ok" ? "connected" : "offline",
                    },
                    {
                      icon: FolderGit2,
                      name: "PostgreSQL + pgvector",
                      detail: `Dedicated local database · vector ${health?.pgvector ?? "unavailable"}`,
                      ready: !!health?.pgvector,
                      state: health?.database ?? "unavailable",
                    },
                    {
                      icon: Sparkles,
                      name: "Google Gemini",
                      detail:
                        health?.gemini_model || "Select a Flash model in .env",
                      ready: !!health?.gemini_configured,
                      state: health?.gemini_configured
                        ? "key configured"
                        : "key needed",
                    },
                    {
                      icon: Code2,
                      name: "Local embedding model",
                      detail:
                        health?.embedding_model ??
                        "Sentence Transformers · CPU inference",
                      ready: ready.length > 0,
                      state: ready.length
                        ? "used for indexing"
                        : "awaiting first index",
                    },
                    {
                      icon: GitBranch,
                      name: "Official GitHub MCP",
                      detail: "Read-only remote MCP · repos and issues tools",
                      ready: !!health?.github_configured,
                      state: health?.github_configured
                        ? "token configured"
                        : "token needed",
                    },
                  ].map((item) => (
                    <div className="setting-row" key={item.name}>
                      <span className="setting-icon">
                        <item.icon size={20} />
                      </span>
                      <div className="row-main">
                        <strong>{item.name}</strong>
                        <small>{item.detail}</small>
                      </div>
                      <span
                        className={
                          "service-state " + (item.ready ? "good" : "")
                        }
                      >
                        {item.ready ? (
                          <CheckCircle2 size={15} />
                        ) : (
                          <Circle size={15} />
                        )}
                        {item.state}
                      </span>
                    </div>
                  ))}
                </div>
              </section>
              <div className="settings-grid">
                <section className="panel settings-card">
                  <ShieldCheck size={24} />
                  <h2>Explicit permission, every time.</h2>
                  <p>
                    All investigations are read-only until you approve a
                    concrete patch. Execution uses named profiles in disposable
                    copies.
                  </p>
                  <div className="permission-row">
                    <span>Local test execution</span>
                    <StatusLabel
                      value={
                        health?.local_test_execution_enabled
                          ? "enabled"
                          : "disabled"
                      }
                    />
                  </div>
                  <div className="permission-row">
                    <span>GitHub draft PR writes</span>
                    <StatusLabel
                      value={
                        health?.github_remote_write_enabled
                          ? "enabled"
                          : "disabled"
                      }
                    />
                  </div>
                  <p className="subtle">
                    Set these switches in the ignored .env file and restart the
                    backend. Native execution is intended for trusted
                    repositories and has no hardened OS sandbox.
                  </p>
                </section>
                <section className="panel settings-card">
                  <Terminal size={24} />
                  <h2>Integration checks</h2>
                  <p>
                    Inspect available Flash models or verify discovery and
                    invocation of the custom MCP server.
                  </p>
                  <div className="button-row">
                    <button
                      className="secondary"
                      disabled={!!busy || !health?.gemini_configured}
                      onClick={() =>
                        void perform("models", async () =>
                          setModelList(
                            (await api<{ models: string[] }>("/config/models"))
                              .models,
                          ),
                        )
                      }
                    >
                      List Gemini models <ArrowUpRight size={14} />
                    </button>
                    <button
                      className="secondary"
                      disabled={!!busy || !selected}
                      onClick={() =>
                        void perform("mcp", async () =>
                          setMcpResult(
                            await api("/config/mcp-check", {
                              repository_id: selected,
                              query: "payment webhook",
                            }),
                          ),
                        )
                      }
                    >
                      Test custom MCP
                    </button>
                  </div>
                  {modelList.length > 0 && (
                    <pre className="tool-output">{modelList.join("\n")}</pre>
                  )}
                  {mcpResult !== null && (
                    <details open>
                      <summary>MCP result</summary>
                      <pre className="tool-output">
                        {JSON.stringify(mcpResult, null, 2)}
                      </pre>
                    </details>
                  )}
                </section>
              </div>
            </>
          )}
          <footer>
            <span>
              <Sparkles size={12} />
              PatchPilot AI
            </span>
            <span>Engineering, with evidence.</span>
            <span>
              <ShieldCheck size={12} aria-hidden="true" />
              Local workspace
            </span>
          </footer>
        </main>
      </div>
      <dialog ref={dialog} className="approval-dialog">
        <div className="dialog-heading">
          <ShieldCheck size={25} />
          <button
            className="icon-button"
            aria-label="Close approval dialog"
            onClick={() => dialog.current?.close()}
          >
            <X size={19} />
          </button>
        </div>
        <h2>
          {approval === "review"
            ? "Approve this proposed patch?"
            : approval === "test"
              ? "Approve this test execution?"
              : "Create this draft pull request?"}
        </h2>
        <p>
          {approval === "review"
            ? "The patch will be marked approved. Test execution and remote publishing require their own approval."
            : approval === "test"
              ? "The exact reviewed patch will be applied to a disposable local copy and the named test command will run. This is a native process, with access to your computer and network."
              : "The reviewed and tested files will be committed to a new codex/patchpilot branch in your authorized Banking App and a draft PR will be created."}
        </p>
        <div className="approval-summary">
          <strong>{repo?.name}</strong>
          <code>
            {approval === "test"
              ? repo?.meta.fixture
                ? "python -I -m unittest discover -s . -v"
                : "mvn -B -f backend/pom.xml test -DfailIfNoTests=false"
              : run?.data.patch?.affected_paths.join("\n")}
          </code>
          <small>Base revision {run?.data.patch?.sha.slice(0, 12)}</small>
        </div>
        <div className="button-row">
          <button className="secondary" onClick={() => dialog.current?.close()}>
            Cancel
          </button>
          <button className="primary" onClick={() => void approveAction()}>
            {approval === "review"
              ? "Approve patch"
              : approval === "test"
                ? "Approve & execute"
                : "Create draft PR"}
            <Check size={15} />
          </button>
        </div>
      </dialog>
    </div>
  );
}
