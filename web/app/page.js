"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
const REPOSITORY_QUERY_BANK = [
  "Where does prod set instance_type?",
  "How does dev differ from prod?",
  "Where does the app get its VPC ID?",
  "Explain the production architecture.",
  "Teach me how values flow between modules in this repository.",
  "Which resources depend on outputs from another module?",
  "Show me the most important environment-specific overrides.",
  "Which configuration would be risky to change without a plan review?",
  "Trace the network configuration from its definition to its consumers.",
  "What reusable modules exist, and where are they called?",
  "Explain the repository structure to someone new to this project.",
  "Which variables have different values in development and production?",
  "Find one important dependency chain and teach me how it works.",
  "What should I inspect first before changing this infrastructure?",
];
const DOCUMENTATION_QUERY_BANK = [
  "Teach me Terraform lifecycle prevent_destroy with an HCL example.",
  "Explain how Terragrunt dependency blocks expose outputs, with an example.",
  "Compare Terraform for_each and count and show when to use each.",
  "Teach me how Terragrunt include configuration works.",
  "Explain Terraform state in plain language and why remote state matters.",
  "Show how Terraform module inputs and outputs work together.",
  "When should I use depends_on, and when should I avoid it?",
  "Teach me Terraform variable validation with a small HCL example.",
  "Explain Terragrunt mock_outputs and when they are useful.",
  "Compare create_before_destroy and prevent_destroy.",
  "How do Terraform data sources differ from managed resources?",
  "Teach me how Terraform conditional expressions work.",
  "Explain Terragrunt run queue ordering and dependency direction.",
  "What are the safest steps for refactoring a Terraform resource address?",
  "Show how a Terraform dynamic block works and explain its tradeoffs.",
  "Teach me how Terragrunt remote state configuration is inherited.",
  "How do preconditions and postconditions improve Terraform safety?",
  "Explain Terraform provider version constraints and lock files.",
];

function randomFive(items) {
  const shuffled = [...new Set(items)];
  for (let index = shuffled.length - 1; index > 0; index -= 1) {
    const other = Math.floor(Math.random() * (index + 1));
    [shuffled[index], shuffled[other]] = [shuffled[other], shuffled[index]];
  }
  return shuffled.slice(0, 5);
}

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
  const pieces = text.split(/(`[^`]+`|\*\*[^*]+\*\*|\*[^*\n]+\*|\[file:[^\]]+\])/g);
  return pieces.map((piece, index) => {
    if (piece.startsWith("`") && piece.endsWith("`")) return <code key={index}>{piece.slice(1, -1)}</code>;
    if (piece.startsWith("**") && piece.endsWith("**")) return <strong key={index}>{piece.slice(2, -2)}</strong>;
    if (piece.startsWith("*") && piece.endsWith("*")) return <em key={index}>{piece.slice(1, -1)}</em>;
    if (piece.startsWith("[file:")) return <span className="inline-citation" key={index}>{piece}</span>;
    return piece;
  });
}

function ProseSection({ text, sectionKey }) {
  const blocks = [];
  let paragraph = [];
  let bullets = [];
  let numbered = [];
  let blockIndex = 0;

  function flushParagraph() {
    if (!paragraph.length) return;
    blocks.push(<p key={`${sectionKey}-p-${blockIndex++}`}><InlineText text={paragraph.join(" ")} /></p>);
    paragraph = [];
  }

  function flushBullets() {
    if (!bullets.length) return;
    blocks.push(<ul key={`${sectionKey}-ul-${blockIndex++}`}>{bullets.map((item, index) => <li key={index}><InlineText text={item} /></li>)}</ul>);
    bullets = [];
  }

  function flushNumbered() {
    if (!numbered.length) return;
    blocks.push(<ol key={`${sectionKey}-ol-${blockIndex++}`}>{numbered.map((item, index) => <li key={index}><InlineText text={item} /></li>)}</ol>);
    numbered = [];
  }

  function flushAll() {
    flushParagraph();
    flushBullets();
    flushNumbered();
  }

  text.split("\n").forEach((line) => {
    const clean = line.trim();
    const heading = clean.match(/^#{1,4}\s+(.+)$/);
    const bullet = clean.match(/^[-*]\s+(.+)$/);
    const ordered = clean.match(/^\d+[.)]\s+(.+)$/);

    if (!clean) return flushAll();
    if (heading) {
      flushAll();
      blocks.push(<h3 key={`${sectionKey}-h-${blockIndex++}`}><InlineText text={heading[1]} /></h3>);
    } else if (bullet) {
      flushParagraph();
      flushNumbered();
      bullets.push(bullet[1]);
    } else if (ordered) {
      flushParagraph();
      flushBullets();
      numbered.push(ordered[1]);
    } else {
      flushBullets();
      flushNumbered();
      paragraph.push(clean);
    }
  });
  flushAll();
  return blocks;
}

function AnswerContent({ text }) {
  const sections = text.split(/```(?:[a-z0-9_-]+)?\n([\s\S]*?)```/gi);
  return <div className="message-body">{sections.map((section, index) => {
    if (index % 2) return <pre key={index}><code>{section.trim()}</code></pre>;
    return <ProseSection text={section} sectionKey={index} key={index} />;
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
  const [suggestions, setSuggestions] = useState([]);
  const [suggestionBatch, setSuggestionBatch] = useState(0);

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

  useEffect(() => {
    setSuggestions([]);
    setSuggestionBatch((current) => current + 1);
  }, [selectedId]);

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
  const repositoryFileQueries = files
    .filter((file) => file.path.endsWith(".tf") || file.path.endsWith(".hcl"))
    .flatMap((file) => [
      `Teach me what ${file.path} configures and why it matters.`,
      `Trace the important values flowing into and out of ${file.path}.`,
    ]);
  const queryPool = isReference ? DOCUMENTATION_QUERY_BANK : [...REPOSITORY_QUERY_BANK, ...repositoryFileQueries];
  const activeSuggestions = suggestions.length ? suggestions : queryPool.slice(0, 5);

  function generateQueries() {
    setSuggestions(randomFive(queryPool));
    setSuggestionBatch((current) => current + 1);
  }

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
            <div><small>QUERY CONSOLE / GROUNDED LEARNING MODE</small><p>Ask what, why, or how. Answers explain the mechanism, show an evidence-based example, and surface caveats.</p></div>
            <div className="mode-flags"><span>SEM</span><span>LEX</span><span>GRAPH</span></div>
          </div>

          <div className="messages" aria-live="polite">
            <section className="query-lab" aria-label="Random query generator">
              <div className="query-lab-heading">
                <div><small>QUERY LAB / EXPLORE THE INDEX</small><p>Generate five prompts, then run any one to get a taught, evidence-grounded answer.</p></div>
                <button type="button" onClick={generateQueries} disabled={selected?.status !== "ready" || Boolean(busy)}><span>↻</span> Generate 5 random queries</button>
              </div>
              <div className="query-lab-grid" key={suggestionBatch}>
                {activeSuggestions.map((item, index) => <button type="button" key={item} disabled={selected?.status !== "ready" || Boolean(busy)} onClick={() => ask(item)}><b>{String(index + 1).padStart(2, "0")}</b><span>{item}</span><i>↗</i></button>)}
              </div>
            </section>
            {!messages.length && <div className="welcome">
              <div className="instruction-grid">
                <div><b>01</b><span>SELECT OR REGISTER<br />A REPOSITORY</span></div>
                <div><b>02</b><span>BUILD THE LOCAL<br />VECTOR INDEX</span></div>
                <div><b>03</b><span>QUERY AND OPEN<br />CITED SOURCE LINES</span></div>
              </div>
              <p className="instruction-note"><b>OPERATOR NOTE</b> Answers are constrained to the selected {isReference ? "official documentation corpus" : "repository evidence"}. TerraRAG performs no write actions against source material.</p>
              <div className="learning-contract" aria-label="How TerraRAG teaches">
                <span>TEACHING OUTPUT</span>
                <div><b>01</b><p>Direct answer<br /><small>start with the conclusion</small></p></div>
                <div><b>02</b><p>Worked example<br /><small>small, cited HCL</small></p></div>
                <div><b>03</b><p>Operational context<br /><small>use cases and caveats</small></p></div>
              </div>
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
            <div><span>Teaching mode · explanation · example · caveats · cited evidence</span><button disabled={!question.trim() || Boolean(busy) || selected?.status !== "ready"}>Ask TerraRAG <b>↗</b></button></div>
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
