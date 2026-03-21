import json

from src.ingestion.skill_taxonomy import (
    RESUME_SKILL_ALIASES, CATEGORY_TO_DOMAIN, SKILL_HIERARCHY,
)

NODE_COLORS = {
    "Engineer": "#c4956a", "Repository": "#6b8f9e",
    "Domain": "#8b7355", "Category": "#b8805a", "Skill": "#7a8b6f",
    "Skill_claimed": "#a8a099", "Skill_gap": "#c4756a",
}
EDGE_COLORS = {
    "owns": "#a8a099", "domain": "#8b7355", "category": "#b8805a", "skill": "#7a8b6f",
}
PROFICIENCY_SIZE = {"extensive": 18, "moderate": 14, "minimal": 10}
LEVEL_MAP = {"eng": 0, "repo": 1, "dom": 2, "cat": 3}


def get_graph_data(neo4j_client):
    nodes, edges = [], []
    node_ids, edge_ids = set(), set()

    def add_node(nid, **kwargs):
        if nid not in node_ids:
            nodes.append({"id": nid, **kwargs})
            node_ids.add(nid)

    def add_edge(from_id, to_id, **kwargs):
        key = (from_id, to_id)
        if key not in edge_ids:
            edges.append({"from": from_id, "to": to_id, **kwargs})
            edge_ids.add(key)

    with neo4j_client.driver.session() as session:
        r = session.run("MATCH (e:Engineer) RETURN e.name AS name").single()
        if r:
            add_node(f"eng:{r['name']}", label=r["name"], color=NODE_COLORS["Engineer"], size=35)

        for r in session.run("MATCH (r:Repository) RETURN r.name AS name"):
            add_node(f"repo:{r['name']}", label=r["name"], color=NODE_COLORS["Repository"], size=22)

        for r in session.run("MATCH (e:Engineer)-[:OWNS]->(r:Repository) RETURN e.name AS eng, r.name AS repo"):
            add_edge(f"eng:{r['eng']}", f"repo:{r['repo']}", color=EDGE_COLORS["owns"])

        for r in session.run(
            "MATCH (d:Domain)-[:CONTAINS]->(c:Category)-[:CONTAINS]->(s:Skill) "
            "WHERE s.proficiency IS NOT NULL AND s.proficiency <> 'none' "
            "RETURN d.name AS domain, c.name AS category, s.name AS skill, s.proficiency AS proficiency"
        ):
            did, cid, sid = f"dom:{r['domain']}", f"cat:{r['category']}", f"skill:{r['skill']}"
            size = PROFICIENCY_SIZE.get(r["proficiency"], 10)
            add_node(did, label=r["domain"], color=NODE_COLORS["Domain"], size=26)
            add_node(cid, label=r["category"], color=NODE_COLORS["Category"], size=18)
            add_node(sid, label=r["skill"], color=NODE_COLORS["Skill"], size=size)
            add_edge(did, cid, color=EDGE_COLORS["domain"])
            add_edge(cid, sid, color=EDGE_COLORS["category"])

        for r in session.run(
            "MATCH (r:Repository)-[:DEMONSTRATES]->(s:Skill) "
            "WHERE s.proficiency IS NOT NULL AND s.proficiency <> 'none' "
            "RETURN r.name AS repo, s.name AS skill"
        ):
            add_edge(f"repo:{r['repo']}", f"skill:{r['skill']}", color=EDGE_COLORS["skill"], dashes=True)

        for r in session.run(
            "MATCH (e:Engineer)-[:CLAIMS]->(s:Skill) "
            "WHERE s.proficiency IS NULL OR s.proficiency = 'none' "
            "RETURN s.name AS skill"
        ):
            add_node(f"skill:{r['skill']}", label=r["skill"], color="#a8a099", size=8)

    for n in nodes:
        prefix = n["id"].split(":")[0]
        n["level"] = LEVEL_MAP.get(prefix, 4)

    return {"nodes": nodes, "edges": edges}


def _top_evidence_links(session, skill_name: str, limit: int = 5) -> list[dict]:
    """Fetch top evidence file links for a skill, ordered by start_line."""
    try:
        rows = session.run(
            "MATCH (f:File)-[:CONTAINS]->(cs:CodeSnippet)-[:DEMONSTRATES]->(s:Skill {name: $name}) "
            "MATCH (r:Repository)-[:CONTAINS]->(f) "
            "RETURN r.name AS repo, f.path AS path, cs.start_line AS line, cs.language AS lang "
            "ORDER BY cs.start_line LIMIT $limit",
            name=skill_name, limit=limit,
        )
        return [
            {"repo": r["repo"], "path": r["path"], "line": r["line"] or 0, "lang": r["lang"] or ""}
            for r in rows
        ]
    except Exception:
        return []


def get_subgraph(neo4j_client, skill_names: list[str]) -> dict:
    if not skill_names:
        return {"nodes": [], "edges": []}
    with neo4j_client.driver.session() as session:
        rows = session.run(
            "MATCH (d:Domain)-[:CONTAINS]->(c:Category)-[:CONTAINS]->(s:Skill) "
            "WHERE s.name IN $names AND s.proficiency IS NOT NULL AND s.proficiency <> 'none' "
            "OPTIONAL MATCH (r:Repository)-[:DEMONSTRATES]->(s) "
            "RETURN d.name AS domain, c.name AS category, s.name AS skill, "
            "s.proficiency AS proficiency, s.snippet_count AS snippet_count, "
            "s.repo_count AS repo_count, collect(DISTINCT r.name) AS repos",
            names=skill_names,
        )
        nodes, edges = [], []
        node_ids, edge_ids = set(), set()
        for r in rows:
            did, cid, sid = f"dom:{r['domain']}", f"cat:{r['category']}", f"skill:{r['skill']}"
            size = PROFICIENCY_SIZE.get(r["proficiency"], 10)
            evidence_links = _top_evidence_links(session, r["skill"])
            for nid, label, color, sz, meta in [
                (did, r["domain"], NODE_COLORS["Domain"], 26, {"type": "domain"}),
                (cid, r["category"], NODE_COLORS["Category"], 18, {"type": "category"}),
                (sid, r["skill"], NODE_COLORS["Skill"], size, {
                    "type": "skill", "status": "demonstrated",
                    "proficiency": r["proficiency"],
                    "evidence_count": r["snippet_count"] or 0,
                    "repo_count": r["repo_count"] or 0,
                    "evidence_links": evidence_links,
                }),
            ]:
                if nid not in node_ids:
                    nodes.append({"id": nid, "label": label, "color": color, "size": sz, "meta": meta})
                    node_ids.add(nid)
            for frm, to, opts in [(did, cid, {}), (cid, sid, {})]:
                if (frm, to) not in edge_ids:
                    edges.append({"from": frm, "to": to, **opts})
                    edge_ids.add((frm, to))
            for repo in r["repos"]:
                rid = f"repo:{repo}"
                if rid not in node_ids:
                    nodes.append({"id": rid, "label": repo, "color": NODE_COLORS["Repository"],
                                  "size": 22, "meta": {"type": "repository"}})
                    node_ids.add(rid)
                if (rid, sid) not in edge_ids:
                    edges.append({"from": rid, "to": sid, "dashes": True})
                    edge_ids.add((rid, sid))
    return {"nodes": nodes, "edges": edges}


def _resolve_alias(name: str) -> tuple[str | None, str | None, str | None]:
    """Resolve a resume alias to (target_skill, category, domain) or (None, category, domain)."""
    alias = RESUME_SKILL_ALIASES.get(name)
    if alias is None:
        return None, None, None
    if alias.startswith("cat:"):
        cat = alias[4:]
        return None, cat, CATEGORY_TO_DOMAIN.get(cat)
    # Direct skill alias — look up its hierarchy
    hier = SKILL_HIERARCHY.get(alias)
    if hier:
        return alias, hier[1], hier[0]
    return None, None, None


def get_gap_overlay(neo4j_client, entity_refs: dict) -> dict:
    """Build graph nodes for claimed-only, gap, and related skills.

    Args:
        entity_refs: dict mapping skill name -> EntityRef (has .name, .status, .related)
    """
    nodes, edges = [], []
    node_ids, edge_ids = set(), set()

    def add_node(nid, **kwargs):
        if nid not in node_ids:
            nodes.append({"id": nid, **kwargs})
            node_ids.add(nid)

    def add_edge(from_id, to_id, **kwargs):
        key = (from_id, to_id)
        if key not in edge_ids:
            edges.append({"from": from_id, "to": to_id, **kwargs})
            edge_ids.add(key)

    for name, ref in entity_refs.items():
        sid = f"skill:{name}"

        if ref.status == "demonstrated":
            continue  # handled by get_subgraph

        if ref.status == "claimed_only":
            target_skill, cat, domain = _resolve_alias(name)

            if target_skill:
                # Near-match alias (e.g., React.js → React): render alias connected to target
                add_node(sid, label=name, color=NODE_COLORS["Skill_claimed"], size=8,
                         meta={"type": "skill", "status": "claimed_only",
                               "alias_of": target_skill, "evidence_count": 0})
                target_sid = f"skill:{target_skill}"
                add_edge(sid, target_sid, dashes=[5, 5], color=NODE_COLORS["Skill_claimed"])
            elif cat and domain:
                # Broad term placed under category (e.g., Python → Web Frameworks)
                did, cid = f"dom:{domain}", f"cat:{cat}"
                add_node(did, label=domain, color=NODE_COLORS["Domain"], size=26,
                         meta={"type": "domain"})
                add_node(cid, label=cat, color=NODE_COLORS["Category"], size=18,
                         meta={"type": "category"})
                add_node(sid, label=name, color=NODE_COLORS["Skill_claimed"], size=8,
                         meta={"type": "skill", "status": "claimed_only",
                               "evidence_count": 0, "placed_under": cat})
                add_edge(did, cid)
                add_edge(cid, sid, dashes=[5, 5])
            else:
                # No alias: floating claimed node
                add_node(sid, label=name, color=NODE_COLORS["Skill_claimed"], size=8,
                         meta={"type": "skill", "status": "claimed_only", "evidence_count": 0})

        elif ref.status == "not_found_but_related":
            add_node(sid, label=name, color=NODE_COLORS["Skill_gap"], size=10,
                     meta={"type": "skill", "status": "gap",
                           "related_demonstrated": ref.related})
            for related_name in ref.related:
                rel_sid = f"skill:{related_name}"
                add_edge(sid, rel_sid, dashes=[2, 4], color=NODE_COLORS["Skill_gap"])

        elif ref.status in ("not_found", "inferred"):
            add_node(sid, label=name, color=NODE_COLORS["Skill_gap"], size=8,
                     meta={"type": "skill", "status": "gap", "evidence_count": 0})

    return {"nodes": nodes, "edges": edges}


def build_query_subgraph(neo4j_client, entity_refs: dict) -> dict:
    """Build a complete subgraph for a query, merging demonstrated skills with gaps.

    Args:
        entity_refs: dict mapping skill name -> EntityRef
    """
    demonstrated = [name for name, ref in entity_refs.items() if ref.status == "demonstrated"]
    base = get_subgraph(neo4j_client, demonstrated)
    overlay = get_gap_overlay(neo4j_client, entity_refs)

    # Merge: base wins on node ID conflict
    base_node_ids = {n["id"] for n in base["nodes"]}
    base_edge_ids = {(e["from"], e["to"]) for e in base["edges"]}

    for node in overlay["nodes"]:
        if node["id"] not in base_node_ids:
            base["nodes"].append(node)
            base_node_ids.add(node["id"])

    for edge in overlay["edges"]:
        key = (edge["from"], edge["to"])
        if key not in base_edge_ids:
            base["edges"].append(edge)
            base_edge_ids.add(key)

    # Assign hierarchical levels
    for n in base["nodes"]:
        if "level" not in n:
            prefix = n["id"].split(":")[0]
            n["level"] = LEVEL_MAP.get(prefix, 4)

    return base


def build_competency_graph(neo4j_client):
    import html as html_mod
    data = get_graph_data(neo4j_client)
    nodes, edges = data["nodes"], data["edges"]

    inner = f"""<!DOCTYPE html>
<html><head>
<script src="https://cdnjs.cloudflare.com/ajax/libs/vis-network/9.1.2/dist/vis-network.min.js"></script>
<style>body{{margin:0;background:#f5f0eb;}} #g{{width:100%;height:580px;}}</style>
</head><body>
<div id="g"></div>
<script>
new vis.Network(document.getElementById("g"),
  {{nodes:new vis.DataSet({json.dumps(nodes)}),edges:new vis.DataSet({json.dumps(edges)}) }},
  {{layout:{{hierarchical:{{enabled:true,direction:"UD",sortMethod:"directed",levelSeparation:140,nodeSpacing:180}}}},
    physics:{{hierarchicalRepulsion:{{springLength:180,nodeDistance:220}},stabilization:{{iterations:150}}}},
    nodes:{{font:{{size:13,color:"#2c2c2c",face:"sans-serif"}},borderWidth:2,shape:"dot"}},
    edges:{{smooth:{{type:"cubicBezier",forceDirection:"vertical",roundness:0.4}},width:1.5}},
    interaction:{{hover:true,zoomView:true,dragView:true,dragNodes:true}}
  }});
</script></body></html>"""
    escaped = html_mod.escape(inner, quote=True)
    return f'<iframe srcdoc="{escaped}" style="width:100%;height:640px;border:none;"></iframe>'
