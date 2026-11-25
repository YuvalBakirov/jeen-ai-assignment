"""Repair pending dependency order when Langflow 1.13.3 resumes a checkpoint."""

from pathlib import Path

path = Path('/app/.venv/lib/python3.14/site-packages/langflow/api/build.py')
source = path.read_text(encoding='utf-8')
needle = '        first_layer = graph.resume_first_layer()\n'
replacement = '''        # Rebuild pending dependency lists after opaque tool outputs are reset.
        # The saved lists were already consumed during the original run.
        excluded = graph.inactivated_vertices | graph.conditionally_excluded_vertices | graph._orphaned_tool_vertex_ids()
        for vertex in graph.vertices:
            if not vertex.built and vertex.id not in excluded:
                graph.run_manager.run_predecessors[vertex.id] = [
                    pred_id for pred_id in graph.predecessor_map.get(vertex.id, [])
                    if pred_id not in excluded and not graph.get_vertex(pred_id).built
                ]
        first_layer = graph.resume_first_layer()
'''
if source.count(needle) != 1:
    raise SystemExit('Unexpected Langflow source; refusing to apply the patch')
path.write_text(source.replace(needle, replacement), encoding='utf-8')
