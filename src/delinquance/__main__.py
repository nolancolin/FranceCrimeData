"""Single entry point: `python -m delinquance <step>`."""

import argparse
import logging

from delinquance import demo, explore, forecast, interpret, obtain, scrub, typology

STEPS = {
    "obtain": obtain.run,
    "scrub": scrub.run,
    "explore": explore.run,
    "typology": typology.run,
    "forecast": forecast.run,
    "interpret": interpret.run,
    "demo": demo.run,
}


def main() -> None:
    parser = argparse.ArgumentParser(prog="delinquance")
    parser.add_argument("step", choices=[*STEPS, "all"])
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    for name, run in STEPS.items():
        if args.step in (name, "all"):
            run()


if __name__ == "__main__":
    main()
