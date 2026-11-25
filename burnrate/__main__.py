"""python -m burnrate  (configuration: BURNRATE_* environment variables, see README)."""
import os, sys, threading
from . import core, engine, server


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
    import faulthandler, signal
    faulthandler.register(signal.SIGUSR1, all_threads=True)     # kill -USR1 <pid>: stack of every thread to stderr
    core.init()
    engine.load_status()
    server.init_auth()
    threading.Thread(target=engine.poller, daemon=True, name="poller").start()
    server.serve()


if __name__ == "__main__":
    main()
