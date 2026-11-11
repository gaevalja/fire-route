"""Actual CSE Group, three display processes, ACKs and stopped-device gate."""
from backend.p1_routes import main as route_main


def main():
    return route_main(with_displays=True)

if __name__ == '__main__':
    raise SystemExit(main())
