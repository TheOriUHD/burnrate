"""python -m burnrate  (configuration: BURNRATE_* environment variables, see README)."""
import os, sys, threading
from . import core, engine, server


def _log_streams():
    """pythonw (Windows, no console) has no stdout/stderr: log to <data>/burnrate.log instead.
    Everywhere: never die on a character the console code page can't show."""
    if sys.stderr is None or sys.stdout is None:
        f = open(os.path.join(core.DATA, "burnrate.log"), "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or f
        sys.stderr = sys.stderr or f
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass


def main():
    os.umask(0o077)
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(__doc__ + "\n\ncommands: (none) serve | providers [--markdown] | demo (seed an empty data dir)\n"
              "env: BURNRATE_DATA, BURNRATE_LISTEN, BURNRATE_PORT, BURNRATE_AUTH=password|none, BURNRATE_PASSWORD")
        return
    if len(sys.argv) > 1 and sys.argv[1] == "providers":
        from .providers import REGISTRY
        ps = sorted(REGISTRY.values(), key=lambda p: (p.category != "subscription", p.name.lower()))
        if "--markdown" in sys.argv:
            kinds = {"fields": "key", "oauth_paste": "sign-in (paste code)", "device": "sign-in (device code)"}
            print("| Provider | Type | What you see | Connect with | Source |\n|---|---|---|---|---|")
            for p in ps:
                auth = ", ".join(dict.fromkeys(a.label if a.kind == "fields" else kinds[a.kind] for a in p.auths))
                print(f"| **{p.name}** | {'subscription' if p.category == 'subscription' else 'API / credits'} | {p.blurb} | "
                      f"{auth} | {'official API' if p.official else 'internal endpoint'} |")
            return
        for p in ps:
            print(f"{p.id:16} {p.name:28} {p.category:13} {'official' if p.official else 'unofficial':10} {p.blurb}")
        return
    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        from . import demo
        demo.run()
        return
    core.init()
    _log_streams()
    try:                                                        # lets the installers stop exactly this process
        with open(os.path.join(core.DATA, "burnrate.pid"), "w") as f:
            f.write(str(os.getpid()))
    except OSError:
        pass
    import faulthandler, signal
    if hasattr(signal, "SIGUSR1"):                              # not on Windows
        faulthandler.register(signal.SIGUSR1, all_threads=True)  # kill -USR1 <pid>: stack of every thread to stderr
    engine.load_status()
    server.init_auth()
    threading.Thread(target=engine.poller, daemon=True, name="poller").start()
    server.serve()


if __name__ == "__main__":
    main()
