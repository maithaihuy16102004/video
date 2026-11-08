import urllib.request, json, sys, time

job_id = "52d57a1cf6"
for i in range(40):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:8787/api/status?id={job_id}") as res:
            data = json.loads(res.read().decode("utf-8"))
            status = data.get("status")
            msg = data.get("message", "")
            sys.stdout.buffer.write(f"[{status}] {msg}\n".encode("utf-8"))
            sys.stdout.flush()
            if status in ("done", "review_required", "failed"):
                break
    except Exception as e:
        print("Poll error:", e)
    time.sleep(5)
