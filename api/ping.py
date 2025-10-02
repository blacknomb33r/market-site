import json
def handler(request):
    return (json.dumps({"ok": True}), 200, {"Content-Type": "application/json"})