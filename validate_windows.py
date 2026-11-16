"""Real packaged stdio/local-model checks. No hosted inference or API keys."""
import json
from pathlib import Path
import subprocess
import time

root = Path(__file__).resolve().parent
home = root.parent / "orchestrator-packaged-validated"
worker = root / "dist/LocalAgentOrchestratorMCP.exe"
process = subprocess.Popen([str(worker), "--home", str(home)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, creationflags=subprocess.CREATE_NO_WINDOW)
counter = 0


def rpc(method, params):
    global counter
    counter += 1
    process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": counter, "method": method, "params": params}) + "\n")
    process.stdin.flush()
    response = json.loads(process.stdout.readline())
    if response.get("result", {}).get("isError") or "error" in response:
        raise RuntimeError(response)
    return response["result"]


def call(name, args):
    return json.loads(rpc("tools/call", {"name": name, "arguments": args})["content"][0]["text"])


def run(model, prompt, criterion, expected, images=None):
    started = time.monotonic()
    task = call("submit_task", {"provider": "ollama", "model": model, "prompt": prompt, "workspace": str(root),
                               "images": images or [], "acceptance_criteria": [criterion]})
    while True:
        task = call("get_task", {"task_id": task["id"]})
        if task["status"] not in ("queued", "running"):
            break
        if time.monotonic() - started > 150:
            raise RuntimeError("Packaged task did not return in its bounded interval")
        time.sleep(.5)
    if task["status"] != "succeeded" or not expected(task["result_text"]):
        raise RuntimeError(json.dumps(task))
    assert task["review_status"] == "pending"
    assert task["lead_id"] == "NeutralLeadValidation"
    reviewed = call("review_task", {"task_id": task["id"], "lead_id": task["lead_id"], "decision": "accepted", "evidence": {
        "summary": "Test client independently checked actual output against its synthetic token/image.",
        "criteria": [{"criterion": criterion, "verdict": "pass", "evidence": "response.md matched the independent expected value/shape-color check"}],
        "boundary_review": "Only local Ollama and explicit synthetic input; cloud_authorized=false; no API keys or outside files.",
        "limitations": ["Representative local protocol check, not validation of every named client or a model benchmark."]}})
    report = {"task_id": task["id"], "selected_model": model, "observed_model": task["observed_model"], "result": task["result_text"],
              "seconds": round(time.monotonic() - started, 2), "lead_id": task["lead_id"], "review_status": reviewed["review_status"]}
    print(json.dumps(report), flush=True)
    return report


try:
    rpc("initialize", {"protocolVersion": "2025-06-18", "clientInfo": {"name": "NeutralLeadValidation"}})
    models = call("list_models", {})
    assert any(m.get("id") == "qwen3:1.7b" and m["provider"] == "ollama" for m in models)
    assert any(m.get("id") == "moondream:latest" and "image" in m["modality"] for m in models)
    results = [run("qwen3:1.7b", "Role: exact token reporter. Objective: return only LOCAL_READY. Source fact: the required token is LOCAL_READY. No tools, extra words or invented checks.",
                   "Returns exactly LOCAL_READY", lambda t: t.strip() == "LOCAL_READY")]
    results.append(run("moondream:latest", "Role: visual observer. Objective: identify the central shape and color in this synthetic image. Reply briefly; no tools or invented tests.",
                       "Identifies a red square in the supplied image", lambda t: "red" in t.lower() and "square" in t.lower(), ["test-assets/red-square.png"]))
    (root / "packaged-live-results.json").write_text(json.dumps({"passed": True, "models_discovered": len(models), "checks": results}, indent=2), encoding="utf-8")
finally:
    process.stdin.close()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.terminate()
