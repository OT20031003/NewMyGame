"""SQLite state checker utility."""

from World import World


def main() -> None:
    world = World(turn_year=3)
    if not world.load():
        print("No SQLite save data found.")
        return

    print(
        f"Loaded: {len(world.Country_list)} countries, "
        f"{len(world.Money_list)} currencies, turn={world.turn}"
    )


if __name__ == "__main__":
    main()
