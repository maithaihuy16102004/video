"""Map-Reduce: tóm tắt từng chunk (Map) rồi gom thành báo cáo (Reduce).

Quy trình đầy đủ:
  log thô -> filter (Lớp 2) -> chunk (Lớp 1) -> map (tóm tắt từng chunk)
          -> reduce (báo cáo Markdown hoàn chỉnh)
"""

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from filter import filter_log
from chunker import smart_chunk
from cache import build_report_system_prompt, build_messages, CacheTracker


def map_summarize(chunks, client, system_prompt, verbose=True):
    """Map: tóm tắt từng chunk thành vài gạch đầu dòng."""
    summaries = []
    for i, chunk in enumerate(chunks):
        msgs = build_messages(
            system_prompt,
            dynamic_content=chunk,
            task_instruction=(
                "Summarize the following log segment into 3-5 concise bullet "
                "points (process name, key events, files, errors). "
                "Return ONLY bullets."
            ),
        )
        r = client.chat(msgs, temperature=0.2, max_tokens=600)
        summaries.append(r["content"])
        if verbose:
            print(f"[ctx-opt] map chunk {i+1}/{len(chunks)} "
                  f"(cache hit {r['cache_hit_ratio']:.0%})")
    return summaries


def reduce_report(summaries, client, system_prompt, project_name,
                  verbose=True):
    """Reduce: gom các tóm tắt thành báo cáo Markdown hoàn chỉnh."""
    combined = "\n\n".join(f"## Segment {i+1}\n{s}"
                           for i, s in enumerate(summaries))
    msgs = build_messages(
        system_prompt,
        dynamic_content=combined,
        task_instruction=(
            f"Combine these segment summaries into ONE clean Markdown daily "
            f"report for the project '{project_name}'. "
            "Sections: # Daily Report, ## Summary, ## By Process, "
            "## Issues (errors/warnings), ## Output Files. Be concise."
        ),
    )
    r = client.chat(msgs, temperature=0.3, max_tokens=2000)
    if verbose:
        print(f"[ctx-opt] reduce done (cache hit {r['cache_hit_ratio']:.0%})")
    return r["content"], r


def generate_daily_report(raw_log, client, project_name="AI Video Editor",
                          chunk_strategy="auto", verbose=True) -> dict:
    """Pipeline đầy đủ: filter -> chunk -> map -> reduce.

    Trả dict: {report, stats, cache_summary}.
    """
    # 1) Lọc (Layer 2)
    cleaned = filter_log(raw_log)

    # 2) Chia chunk (Layer 1)
    chunks = smart_chunk(cleaned, strategy=chunk_strategy)

    # 3) System prompt tĩnh (Layer 3 — cache-friendly)
    system_prompt = build_report_system_prompt(project_name)

    # Nếu log nhỏ (1 chunk) -> bỏ map, gọi 1 lần reduce duy nhất
    if len(chunks) == 1:
        msgs = build_messages(system_prompt, dynamic_content=cleaned)
        r = client.chat(msgs, temperature=0.3, max_tokens=2000)
        report = r["content"]
        stats = {
            "raw_chars": len(raw_log),
            "cleaned_chars": len(cleaned),
            "reduction_pct": round((1 - len(cleaned) / max(1, len(raw_log))) * 100, 1),
            "num_chunks": 1,
            "map_calls": 0,
        }
        return {
            "report": report,
            "stats": stats,
            "cache_summary": client.summary(),
        }

    # 4) Map
    summaries = map_summarize(chunks, client, system_prompt, verbose)

    # 5) Reduce
    report, r = reduce_report(summaries, client, system_prompt, project_name, verbose)

    stats = {
        "raw_chars": len(raw_log),
        "cleaned_chars": len(cleaned),
        "reduction_pct": round((1 - len(cleaned) / max(1, len(raw_log))) * 100, 1),
        "num_chunks": len(chunks),
        "map_calls": len(chunks),
    }
    return {
        "report": report,
        "stats": stats,
        "cache_summary": client.summary(),
    }
