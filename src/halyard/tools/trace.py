"""Trace an ID back to the file and row it came from, and show how each value was obtained."""

from __future__ import annotations

from collections import Counter
from typing import Any

from halyard.store.graph_store import NodeView
from halyard.store.schema import NODE_PROVENANCE, NODES
from halyard.tools.base import ToolResult
from halyard.tools.context import ToolContext
from halyard.tools.log import RESULT_PREFIX, find

# Node types an ID is looked up in, in this order.
TRACEABLE = ("Mention", "Ad", "Observation", "Product", "ComplaintCode", "Brand", "ProductLine",
             "Source")  # fmt: skip
MAX_EDGES = 50  # a brand has thousands of edges; beyond this they are counted, not listed
EDGE_DETAIL = ("method", "rule", "model", "matched", "basis", "reason", "source_ref",
               "captured_at")  # fmt: skip


def _how(label: str, node: NodeView) -> dict[str, dict[str, Any]]:
    """Each property with how it was obtained: extracted, inferred by a rule, or config."""
    declared = NODES[label].properties
    rules = dict(p.split(":", 1) for p in node.props.get("inferred_properties", []))
    values = {}
    for name in declared:  # in the ontology's order, whatever order the store returns
        if name in node.props and name not in NODE_PROVENANCE:
            how = f"inferred ({rules[name]})" if name in rules else declared[name][0]
            values[name] = {"value": node.props[name], "how": how}
    return values


def _node(label: str, node: NodeView) -> dict[str, Any]:
    traced: dict[str, Any] = {
        "id": node.key,
        "type": label,
        "source_file": node.props.get("source_file"),
        "source_ref": node.props.get("source_ref"),
    }
    if "source_rows" in node.props:  # D-10: every row of the export holding this mention
        traced["source_rows"] = node.props["source_rows"]
    traced["values"] = _how(label, node)
    if len(node.edges) > MAX_EDGES:
        traced["edge_counts"] = dict(
            Counter(f"{e.kind} ({e.direction})" for e in node.edges).most_common()
        )
    else:
        traced["edges"] = [
            {"edge": e.kind, "direction": e.direction, "node": f"{e.other[0]} {e.other[1]}"}
            | {k: e.props[k] for k in EDGE_DETAIL if k in e.props}
            for e in node.edges
        ]
    return {k: v for k, v in traced.items() if v is not None}


def _result(entry: dict[str, Any]) -> dict[str, Any]:
    result = entry["result"]
    return {
        "id": entry["result_id"],
        "type": "tool result",
        "tool": entry["tool"],
        "arguments": entry["args"],
        "called_at": entry["at"],
        "method_note": result["method_note"],
        "as_of": result["as_of"],
        "mention_ids": result["mention_ids"],
        "source_refs": result["source_refs"],
    }


def trace(ctx: ToolContext, ids: list[str]) -> ToolResult:
    traced, not_found, mention_ids, source_refs = [], [], [], []
    for item in dict.fromkeys(ids):
        if item.startswith(RESULT_PREFIX):
            entry = find(ctx.tool_log, item)
            if entry:
                traced.append(_result(entry))
            else:
                not_found.append(item)
            continue
        for label in TRACEABLE:
            node = ctx.store.node(label, item)
            if node is None:
                continue
            row = _node(label, node)
            traced.append(row)
            file = row.get("source_file")
            if label == "Mention":
                mention_ids.append(item)
                source_refs += [f"{file}:{r}" for r in row["source_rows"]]
            elif "source_ref" in row:
                source_refs.append(row["source_ref"])
            break
        else:
            not_found.append(item)
    note = (
        "Each node gives the file and row it was read from. A value marked `extracted` is "
        "copied from the source; `inferred` names the rule in docs/definitions.md that "
        "computed it; `config` is our own configuration. Each edge carries the source row or "
        "mention it rests on and, when inferred, its rule or model and the text that matched. "
        "A tool result gives the original call and every mention ID it counted."
    )
    return ToolResult(
        {"traced": traced, "not_found": not_found}, note, ctx.client.as_of,
        mention_ids=mention_ids, source_refs=source_refs,
    )  # fmt: skip


# --- for the command line -------------------------------------------------------------


def _short(value: Any, width: int = 90) -> str:
    text = str(value).replace("\n", " ")
    return text if len(text) <= width else text[: width - 1] + "…"


def render_trace(data: dict[str, Any]) -> str:
    """A trace as text for `halyard trace`. Takes ToolResult.to_dict()["data"]."""
    out: list[str] = []
    for t in data["traced"]:
        if t["type"] == "tool result":
            out += [
                f"{t['id']}  result of {t['tool']}  called {t['called_at']}",
                f"  arguments: {t['arguments']}",
                (f"  as of {t['as_of']}; {len(t['mention_ids'])} mention IDs, "
                 f"{len(t['source_refs'])} source rows"),
                f"  method: {t['method_note']}",
                f"  mention IDs: {_short(', '.join(t['mention_ids']), 200)}",
                "",
            ]
            continue
        rows = t.get("source_rows")
        where = (
            f"{t.get('source_file')} rows {', '.join(map(str, rows))}" if rows
            else t.get("source_ref") or t.get("source_file") or "no source"
        )  # fmt: skip
        out.append(f"{t['id']}  {t['type']}  {where}")
        for name, v in t["values"].items():
            out.append(f"  {name} = {_short(v['value'])}   [{v['how']}]")
        for e in t.get("edges", []):
            arrow = "->" if e["direction"] == "out" else "<-"
            detail = ", ".join(
                f"{k} {_short(e[k], 40)}" for k in EDGE_DETAIL if k in e and k != "reason"
            )
            out.append(f"  {e['edge']} {arrow} {e['node']}   [{detail}]")
        for kind, n in t.get("edge_counts", {}).items():
            out.append(f"  {n} x {kind}")
        out.append("")
    if data["not_found"]:
        out.append("Not found: " + ", ".join(data["not_found"]))
    return "\n".join(out).rstrip()
