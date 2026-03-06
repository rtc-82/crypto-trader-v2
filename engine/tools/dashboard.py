import time
import os
import json
from datetime import datetime

STATE_FILE = "engine_state.json"

start_time = time.time()


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def load_state():

    if not os.path.exists(STATE_FILE):
        return None

    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return None


def format_runtime():

    runtime = int(time.time() - start_time)

    hours = runtime // 3600
    minutes = (runtime % 3600) // 60
    seconds = runtime % 60

    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def draw():

    state = load_state()

    clear()

    print("====================================")
    print("        CRYPTO TRADER V2")
    print("====================================\n")

    print(f"Runtime:       {format_runtime()}")

    if not state:
        print("\nWaiting for engine state...")
        print("\n(Engine may still be starting)\n")
        return

    equity = state.get("total_equity", 0)
    peak = state.get("peak_equity", 0)

    drawdown = 0
    if peak > 0:
        drawdown = (peak - equity) / peak * 100

    chains = state.get("chains", {})

    print(f"Equity:        {equity:,.2f}")
    print(f"Peak Equity:   {peak:,.2f}")
    print(f"Drawdown:      {drawdown:.2f}%\n")

    print("Chains")
    print("----------------------------------------------------------")
    print("CHAIN    POSITION   SIZE        REALIZED     UNREALIZED")

    open_positions = 0
    total_realized = 0
    total_unreal = 0

    for name, c in chains.items():

        pos = c.get("position")
        size = c.get("position_size")
        realized = c.get("realized_pnl", 0)
        unreal = c.get("unrealized_pnl", 0)

        if pos:
            open_positions += 1

        total_realized += realized
        total_unreal += unreal

        size_str = f"{size:.4f}" if size else "-"

        print(
            f"{name:8} "
            f"{str(pos):8} "
            f"{size_str:10} "
            f"{realized:10.2f} "
            f"{unreal:12.2f}"
        )

    print("\n----------------------------------------------------------")

    print(f"Open Positions:   {open_positions}")
    print(f"Total Realized:   {total_realized:.2f}")
    print(f"Total Unrealized: {total_unreal:.2f}")

    print("\nUpdated:", datetime.utcnow().strftime("%H:%M:%S UTC"))

    print("\n====================================")


def run():

    while True:

        draw()

        time.sleep(2)


if __name__ == "__main__":

    run()