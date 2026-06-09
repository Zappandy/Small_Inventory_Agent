from __future__ import annotations

import argparse
from pathlib import Path

import modal


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}

    if not path.exists():
        return values

    for line in path.read_text().splitlines():
        stripped = line.strip()

        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")

    return values


def write_env(path: Path, values: dict[str, str]) -> None:
    lines = []

    for key in sorted(values):
        value = values[key]
        lines.append(f'{key}="{value}"')

    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", required=True)
    parser.add_argument("--function", required=True)
    parser.add_argument("--route", default="/extract")
    parser.add_argument("--env-var", default="MODAL_RECEIPT_ENDPOINT")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--also", nargs="*", default=[])

    args = parser.parse_args()

    remote_function = modal.Function.from_name(args.app, args.function)
    base_url = remote_function.get_web_url().rstrip("/")
    endpoint_url = base_url + args.route

    env_path = Path(args.env_file)
    values = read_env(env_path)

    values[args.env_var] = endpoint_url

    for extra_key in args.also:
        values[extra_key] = endpoint_url

    write_env(env_path, values)

    print(f"Wrote {args.env_var}={endpoint_url} to {env_path}")

    for extra_key in args.also:
        print(f"Wrote {extra_key}={endpoint_url} to {env_path}")


if __name__ == "__main__":
    main()
