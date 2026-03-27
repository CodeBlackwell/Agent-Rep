# Changelog

All notable changes to PROVE are documented here.

## [0.9.2] — 2026-03-26

### Changed
- **Workshop intro rewrite** — replaced numbered step list with flowing Cormorant Garamond prose; reads like a craftsperson's inscription, not a product tour
- Diamond ornament separator between title and body text
- All workshop text now in serif (Cormorant Garamond) for cohesive voice
- Warmer brown palette across workshop intro (`#5a4a3a` body, `#3d2e1e` title, `--accent` CTA)
- Staggered fade-in reveal on workshop elements matching hero animation pattern
- Increased donut tile canvas from 110px to 126px (+15%)
- Larger font sizes and more generous line spacing throughout workshop section

## [0.9.1] — 2026-03-25

### Changed
- Reduced repo-tile hover zoom from 1.5x to 1.25x for subtler interaction
- Bolder exhibit header (weight 700, wider letter-spacing)
- Larger, bolder repo-tile names (0.88rem, weight 700, darker ink)

## [0.9.0] — 2026-03-25

### Added
- **Static build pipeline** — esbuild minification for JS/CSS, brotli/gzip pre-compression, custom D3 bundle (`scripts/build-static.sh`)
- **Lazy-load mermaid** — CDN script loaded on first diagram render instead of on page load
- **Lazy-load hljs** — IntersectionObserver defers syntax highlighting until code blocks scroll into view
- **SSE render debounce** — buffer text updates and flush at requestAnimationFrame rate

### Performance
- **Route interception** in E2E tests — fetch page HTML once, serve from memory via `page.route()`
- **Class-scoped shared pages** — read-only test classes share one Playwright page per device instead of creating/destroying per test (~80 fewer page creates across 355 tests)

## [0.8.0] — 2026-03-24

### Added
- **Repo donut tiles** — circular project breakdowns in graph panel showing skill distribution per repo
- **Exhibits tab** — replaced Bars tab with showcase tiles, dynamic legend, responsive flexbox layout
- **Donut detail modal** — accordion skill lists with lazy snippet loading, glassmorphic styling
- **Mermaid lightbox** — click-to-expand mermaid diagrams in evidence panel
- **Repo-stripe treemap** — color-coded tiles by repository with smooth tooltip tracking
- **Display names** for repos, Veridatum added to showcase, web links in detail view

### Changed
- Extracted Caddy to standalone gateway repo, marked web network external
- Unified all modals with repo-detail glass aesthetic

### Fixed
- Smooth tooltip tracking with dynamic orientation and themed scrollbars
- Missing closing brace in viz-tooltip CSS that broke subsequent rules
- Responsive tile layout overlap with howto content

## [0.7.0] — 2026-03-23

### Added
- **Mobile E2E test suite** — 355 Playwright tests across 8 devices (iPhone 15, Pixel 7, Galaxy S23, iPad Mini, Firefox Mobile, etc.)
- **Collapsible code blocks** with syntax highlighting in chat responses
- **Clickable confidence badges** — open evidence panel with private repo redacted tags
- **Hash-based snippet diffing** in ingestion pipeline — skip unchanged code on re-ingest
- **Send button** in chat form, reordered as upload|input|send
- **Auto cache-bust** — static assets use content hash instead of manual version bumps

### Changed
- Skills ranked by breadth × depth instead of raw count
- Log scale for treemap tile sizing so high-volume skills don't dominate
- Mobile breakpoint extended to 1024px for iPad portrait; graph panel visible on tablets, hidden on phones (<480px)

### Fixed
- iOS zoom prevention on all inputs (font-size >= 16px)
- JD button cutoff on mobile from cascade ordering
- API retry logic, Neo4j session handling, evidence ordering
- Canvas transitions and mobile overflow

## [0.6.0] — 2026-03-22

### Added
- **Architecture deep-dives** — mermaid diagrams in agent responses, pre-seeded per repo
- **Notebook parsing** — Jupyter `.ipynb` files now ingested alongside Python source
- **Starter questions** — three tappable prompts on first load
- **PROVE tagline** with staggered reveal animation
- **Open Graph + Twitter Card** meta tags for rich link previews
- **Comprehensive SEO** — JSON-LD structured data, canonical URLs, meta descriptions
- **Bot exemption** from rate limiting (Googlebot, Twitterbot, etc.)

### Changed
- Mobile layout: chat-only with smooth hero fade, content-driven height
- Replaced manual cache busting with ETag revalidation

### Fixed
- Hero justified to top, chat to bottom with space-between on mobile
- Chat panel shrink-wraps initially, expands after first query
- Deploy reads `.env` via justfile dotenv-load

## [0.5.0] — 2026-03-21

### Added
- **Structured logger** — session auditing, cost tracking, per-model pricing, JSONL + SQLite output
- **Context-augmented embeddings** — Sonnet generates a dense paragraph per snippet before embedding
- **Conversation history** — multi-turn Q&A with SQLite persistence, 20-turn max per session
- **Rate limiting** — per-visitor sliding window with browser fingerprinting (canvas hash, screen, timezone)
- **Treemap + bar visualizations** — domain-colored skill hierarchy with tooltip evidence links
- **ReferenceIndex modal** — filterable evidence browser with per-repo default branch
- **Da Vinci notebook UI** — glassmorphic panels over background illustration
- **Loading screen + canvas toggle** — domain filter pills, reveal animation
- **Private repo controls** — `SHOW_PRIVATE_CODE` toggle, tool-level code redaction
- **JD match accordions** — per-requirement confidence with expandable details
- **CDN infrastructure** — SVGO optimization, CloudFront distribution, cache headers
- **Neo4j backup/restore** to Hetzner Object Storage
- **Production deployment** — Docker Compose with Caddy auto-HTTPS

### Changed
- Default to Anthropic+Voyage pipeline; Haiku 4.5 for queries, Sonnet locked for ingestion
- Demote test files in vector search, increase top_k to 25
- Renamed ShowMeOff to PROVE across entire codebase

### Fixed
- Evidence diversity and answer brevity in QA responses
- Auto-batch Voyage embeds, reuse existing context in ingestion
- Skip nested git repos and already-embedded snippets during ingestion
- Mobile viewport bleed, canvas toggle panel synchronization

## [0.4.0] — 2026-03-20

### Added
- **Dual-provider pipeline** — toggleable NIM (free) and Anthropic+Voyage (quality) backends via env vars
- **Skill-aware prompts** — agent uses taxonomy context for better evidence curation
- **Repo architecture tool** — agent can retrieve pre-seeded architecture summaries

### Changed
- Full platform integration: ingestion, QA agent, JD match, and UI wired together

## [0.3.0] — 2026-03-19

### Added
- **Ingestion pipeline** — tree-sitter parser, LLM skill extraction, Neo4j graph builder, resume parser
- **QA agent** — ReAct loop with Nemotron, evidence-cited responses, SSE streaming
- **JD match** — requirement parser, evidence matcher, match report generator
- **Neo4j schema** — Engineer → Repository → File → CodeSnippet → Skill graph with domain taxonomy
- **NVIDIA NIM client** — Nemotron chat + EmbedQA embeddings
- Project scaffolding with uv, Docker Compose for Neo4j
