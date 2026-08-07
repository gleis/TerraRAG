"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
const STARTERS = [
  "Where does prod set instance_type?",
  "How does dev differ from prod?",
  "Where does the app get its VPC ID?",
  "Explain the production architecture.",
];
const DOC_STARTERS = [
  "What does Terraform lifecycle prevent_destroy do?",
  "How do Terragrunt dependency blocks expose outputs?",
  "How does Terraform for_each differ from count?",
  "How does Terragrunt include configuration work?",
];

async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `${response.status} ${response.statusText}`);
  return body;
}

function StatusLight({ ok }) {
  return <i className={ok ? "light is-on" : "light"} aria-hidden="true" />;
}

function FileGlyph({ language }) {
  return <span className={`file-glyph ${language}`}>{language === "terragrunt" ? "TG" : language === "terraform" ? "TF" : language === "markdown" ? "MD" : "·"}</span>;
}

function InlineText({ text }) {
  const pieces = text.split(/(`[^`]+`|\*\*[^*]+\*\*|\[file:[^\]]+\])/g);
  return pieces.map((piece, index) => {
    if (piece.startsWith("`") && piece.endsWith("`")) return <code key={index}>{piece.slice(1, -1)}</code>;
    if (piece.startsWith("**") && piece.endsWith("**")) return <strong key={index}>{piece.slice(2, -2)}</strong>;
    if (piece.startsWith("[file:")) return <span className="inline-citation" key={index}>{piece}</span>;
    return piece;
  });
}

function AnswerContent({ text }) {
  const sections = text.split(/```(?:[a-z0-9_-]+)?\n([\s\S]*?)```/gi);
  return <div className="message-body">{sections.map((section, index) => {
    if (index % 2) return <pre key={index}><code>{section.trim()}</code></pre>;
    return section.split(/\n\s*\n/).filter(Boolean).map((paragraph, paragraphIndex) => (
      <p key={`${index}-${paragraphIndex}`}><InlineText text={paragraph} /></p>
    ));
  })}</div>;
}

function SourceViewer({ source, onClose }) {
  const selectedLineRef = useRef(null);
  useEffect(() => {
    if (!source) return;
    const frame = requestAnimationFrame(() => selectedLineRef.current?.scrollIntoView({ block: "center" }));
    return () => cancelAnimationFrame(frame);
  }, [source]);
  if (!source) return null;
  const lines = source.content.split("\n");
  const start = source.start_line || 0;
  const end = source.end_line || 0;
  return (
    <div className="source-overlay" role="dialog" aria-modal="true" aria-label={`Source: ${source.path}`}>
      <section className="source-panel">
        <header>
          <div><span>SOURCE EVIDENCE</span><strong>{source.path}</strong></div>
          <button onClick={onClose} aria-label="Close source viewer">Close ×</button>
        </header>
        <pre>{lines.map((line, index) => {
          const number = index + 1;
          const selected = start && number >= start && number <= end;
          return <span ref={selected && number === start ? selectedLineRef : null} className={selected ? "source-line selected" : "source-line"} key={number}><b>{String(number).padStart(3, "0")}</b><code>{line || " "}</code></span>;
        })}</pre>
      </section>
    </div>
  );
}

export default function Home() {
  const [health, setHealth] = useState(null);
  const [repositories, setRepositories] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [repoPath, setRepoPath] = useState("example-infra");
  const [files, setFiles] = useState([]);
  const [graph, setGraph] = useState([]);
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [inspector, setInspector] = useState(null);
  const [source, setSource] = useState(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  const selected = useMemo(() => repositories.find((repo) => repo.id === selectedId), [repositories, selectedId]);

  const refreshRepositories = useCallback(async () => {
    const items = await request("/repositories");
    setRepositories(items);
    setSelectedId((current) => current || items[0]?.id || "");
    return items;
  }, []);

  useEffect(() => {
    request("/health").then(setHealth).catch((reason) => setError(reason.message));
    refreshRepositories().catch((reason) => setError(reason.message));
  }, [refreshRepositories]);

  useEffect(() => {
    if (!selectedId || selected?.status !== "ready") {
      setFiles([]);
      setGraph([]);
      return;
    }
    Promise.all([
      request(`/repositories/${selectedId}/files`),
      request(`/repositories/${selectedId}/graph`),
    ]).then(([nextFiles, nextGraph]) => {
      setFiles(nextFiles);
      setGraph(nextGraph);
    }).catch((reason) => setError(reason.message));
  }, [selectedId, selected?.status]);

  async function registerRepository(event) {
    event.preventDefault();
    setBusy("registering");
    setError("");
    try {
      const repo = await request("/repositories", { method: "POST", body: JSON.stringify({ path: repoPath }) });
      await refreshRepositories();
      setSelectedId(repo.id);
    } catch (reason) {
      setError(reason.message);
    } finally {
      setBusy("");
    }
  }

  async function indexRepository() {
    if (!selectedId) return;
    setBusy("indexing");
    setError("");
    setRepositories((items) => items.map((item) => item.id === selectedId ? { ...item, status: "indexing" } : item));
    try {
      const updated = await request(`/repositories/${selectedId}/index`, { method: "POST" });
      setRepositories((items) => items.map((item) => item.id === selectedId ? updated : item));
    } catch (reason) {
      setError(reason.message);
      await refreshRepositories();
    } finally {
      setBusy("");
    }
  }

  async function ask(text = question) {
    const clean = text.trim();
    if (!clean || !selectedId || selected?.status !== "ready") return;
    setQuestion("");
    setBusy("thinking");
    setError("");
    setMessages((items) => [...items, { role: "user", content: clean }]);
    try {
      const response = await request("/chat", {
        method: "POST",
        body: JSON.stringify({ repository_id: selectedId, question: clean }),
      });
      setMessages((items) => [...items, { role: "assistant", content: response.answer, model: response.model }]);
      setInspector(response);
    } catch (reason) {
      setError(reason.message);
      setMessages((items) => [...items, { role: "assistant", content: `Request failed: ${reason.message}` }]);
    } finally {
      setBusy("");
    }
  }

  async function openSource(item) {
    try {
      const body = await request(`/repositories/${selectedId}/source?path=${encodeURIComponent(item.file_path || item.path)}`);
      setSource({ ...body, start_line: item.start_line, end_line: item.end_line });
    } catch (reason) {
      setError(reason.message);
    }
  }

  const ready = health?.status === "ready";
  const isReference = selected?.root_path === "reference-docs";
  const activeStarters = isReference ? DOC_STARTERS : STARTERS;

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand"><span className="brand-mark">TR</span><div><strong>TERRARAG</strong><small>// LOCAL IAC ANALYSIS</small></div></div>
        <div className="runtime"><span className="runtime-label">SYS</span><StatusLight ok={ready} /><span>{ready ? "READY" : "DEGRADED"}</span><b>LOCAL · PRIVATE</b></div>
      </header>

      {error && <div className="error-banner"><span>ATTENTION</span>{error}<button onClick={() => setError("")}>×</button></div>}

      <div className="workspace">
        <aside className="repository-rail">
          <div className="rail-title"><span>01</span><div><small>{isReference ? "OFFICIAL REFERENCE CORPUS" : "REPOSITORY CONTROL"}</small><strong>{selected?.name || "NO SOURCE MOUNTED"}</strong></div></div>

          <label className="select-label">Active index
            <select value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>
              <option value="">Select repository</option>
              {repositories.map((repo) => <option value={repo.id} key={repo.id}>{repo.name}</option>)}
            </select>
          </label>

          <form className="register-form" onSubmit={registerRepository}>
            <label>Path below /repos<input value={repoPath} onChange={(event) => setRepoPath(event.target.value)} placeholder="example-infra" /></label>
            <button disabled={Boolean(busy)}>{busy === "registering" ? "Registering…" : "Register path"}</button>
          </form>

          {selected && <div className="index-block">
            <div><span className={`repo-state ${selected.status}`}>{selected.status}</span><span>{selected.file_count} files · {selected.chunk_count} {isReference ? "sections" : "objects"}</span></div>
            {isReference && <span className="corpus-badge">OFFICIAL · VERSION PINNED · READ ONLY</span>}
            <code>REPO_ID/{selected.id}</code>
            <button className="index-button" onClick={indexRepository} disabled={Boolean(busy)}>{busy === "indexing" ? "Embedding repository…" : selected.status === "ready" ? "Re-index" : "Build index"}</button>
          </div>}

          <div className="file-list">
            <div className="file-list-heading"><span>Indexed source</span><b>{files.length}</b></div>
            {files.map((file) => <button key={file.path} onClick={() => openSource(file)}><FileGlyph language={file.language} /><span>{file.path}</span></button>)}
            {!files.length && <p className="empty-copy">Register and index a repository to inspect its source tree.</p>}
          </div>
        </aside>

        <section className="conversation">
          <div className="conversation-heading">
            <span>02</span>
            <div><small>QUERY CONSOLE / GROUNDED MODE</small><p>Select an indexed repository, enter a question, then inspect the ranked evidence at right.</p></div>
            <div className="mode-flags"><span>SEM</span><span>LEX</span><span>GRAPH</span></div>
          </div>

          <div className="messages" aria-live="polite">
            {!messages.length && <div className="welcome">
              <div className="instruction-grid">
                <div><b>01</b><span>SELECT OR REGISTER<br />A REPOSITORY</span></div>
                <div><b>02</b><span>BUILD THE LOCAL<br />VECTOR INDEX</span></div>
                <div><b>03</b><span>QUERY AND OPEN<br />CITED SOURCE LINES</span></div>
              </div>
              <p className="instruction-note"><b>OPERATOR NOTE</b> Answers are constrained to the selected {isReference ? "official documentation corpus" : "repository evidence"}. TerraRAG performs no write actions against source material.</p>
              <small className="example-label">EXAMPLE QUERIES</small>
              <div className="starters">{activeStarters.map((item) => <button key={item} disabled={selected?.status !== "ready" || Boolean(busy)} onClick={() => ask(item)}>{item}<span>↗</span></button>)}</div>
            </div>}
            {messages.map((message, index) => <article className={`message ${message.role}`} key={`${message.role}-${index}`}>
              <small>{message.role === "user" ? "QUESTION" : `TERRARAG · ${message.model || "LOCAL"}`}</small>
              {message.role === "assistant" ? <AnswerContent text={message.content} /> : <p>{message.content}</p>}
            </article>)}
            {busy === "thinking" && <article className="message assistant thinking"><small>TERRARAG · RETRIEVING</small><p><i /> Fusing semantic, lexical, and structural evidence…</p></article>}
          </div>

          <form className="question-box" onSubmit={(event) => { event.preventDefault(); ask(); }}>
            <label htmlFor="repository-query">QUERY_INPUT</label>
            <textarea id="repository-query" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder={selected?.status === "ready" ? isReference ? "Ask about Terraform or Terragrunt behavior, syntax, commands, or patterns…" : "Ask about resources, inputs, inheritance, or dependencies…" : "Index a repository before asking questions"} disabled={selected?.status !== "ready" || Boolean(busy)} rows={3} />
            <div><span>{isReference ? "Official versioned documentation only" : "Repository evidence only"} · no write actions</span><button disabled={!question.trim() || Boolean(busy) || selected?.status !== "ready"}>Ask TerraRAG <b>↗</b></button></div>
          </form>
        </section>

        <aside className="inspector">
          <div className="rail-title"><span>03</span><div><small>RETRIEVAL TRACE</small><strong>EVIDENCE / RANK / SOURCE</strong></div></div>

          {inspector ? <>
            <div className="metric-grid">
              <div><b>{inspector.retrieval.semantic_candidates}</b><span>semantic</span></div>
              <div><b>{inspector.retrieval.keyword_hits}</b><span>keyword</span></div>
              <div><b>{inspector.retrieval.structural_edges_used}</b><span>edges</span></div>
              <div><b>{inspector.sources.length}</b><span>used</span></div>
            </div>
            <div className="evidence-list">
              {inspector.sources.map((item, index) => <button key={item.id} onClick={() => openSource(item)}>
                <span className="evidence-index">{String(index + 1).padStart(2, "0")}</span>
                <div><strong>{item.address || item.object_name}</strong><p>{item.file_path}</p><small>LINES {item.start_line}–{item.end_line}</small><div className="method-tags">{item.methods.map((method) => <i key={method}>{method}</i>)}</div></div>
                <b>↗</b>
              </button>)}
            </div>
          </> : <div className="inspector-empty">
            <div className="pipeline"><span>QUERY</span><i>→</i><span>SEM + FTS</span><i>→</i><span>GRAPH</span><i>→</i><span>LLM</span></div>
            <p>Submit a query to populate the retrieval trace.</p>
            <ul><li>Compare candidate and evidence counts.</li><li>Open any evidence row at its cited line range.</li><li>Use the method tags to inspect how each result ranked.</li></ul>
          </div>}

          <div className="graph-summary"><span>{isReference ? "CORPUS PROVENANCE" : "STRUCTURAL INDEX"}</span><strong>{isReference ? "Terraform 1.15 · Terragrunt 1.1" : `${graph.length} relationships`}</strong><p>{isReference ? "official upstream · pinned commits · exact source lines" : "references · includes · dependencies · feeds · module sources"}</p></div>
        </aside>
      </div>

      <SourceViewer source={source} onClose={() => setSource(null)} />
    </main>
  );
}
