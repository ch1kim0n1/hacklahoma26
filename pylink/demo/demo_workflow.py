from core.context.session import SessionContext
from core.executor.engine import ExecutionEngine
from core.input.text_input import read_text_input
from core.nlu.parser import parse_intent
from core.planner.action_planner import ActionPlanner
from core.safety.guard import KillSwitch, SafetyGuard


def run_demo() -> None:
    print("PixelLink demo: try 'open notes' or 'type hello world'.")
    session = SessionContext()
    guard = SafetyGuard()
    kill_switch = KillSwitch()
    kill_switch.start()
    planner = ActionPlanner()
    executor = ExecutionEngine(kill_switch)

    data = read_text_input()
    raw_text = data["raw_text"] or "open Notes"

    intent = parse_intent(raw_text, session)
    print(f"Parsed intent: {intent}")

    steps = planner.plan(intent, session, guard)
    print("Planned steps:")
    for index, step in enumerate(steps, start=1):
        print(f"  {index}. {step.action} - {step.description}")

    safety = guard.validate_plan(steps)
    if not safety.allowed:
        print(safety.reason)
        return

    result = executor.execute_steps(steps, guard)
    if result.pending_steps:
        print("Demo stopped awaiting confirmation.")
    else:
        print("Demo completed.")
    kill_switch.stop()


if __name__ == "__main__":
    run_demo()
