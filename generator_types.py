from dataclasses import dataclass
from typing import Callable, List, Union


@dataclass
class Generator:
    name: str
    source_filter: Union[Callable[[], str], str, None] = None
    include: Union[List[str], None] = None
    color_ramp: Union[str, None] = "Greys"
    single_color: str = "gray"

    def __post_init__(self):
        if isinstance(self.source_filter, str):
            old_source = self.source_filter

            self.source_filter = lambda: old_source
            return

        # If include is provided but source_filter is not a callable, create a filter function
        if not callable(self.source_filter):
            if self.include is not None:
                self.source_filter = lambda: (
                    f"""array_contains(array({', '.join([f"'{x}'" for x in self.include])}), "Energy Source Code")"""
                    if len(self.include) > 1
                    else f""""Energy Source Code" = '{self.include[0]}'"""
                )


# Create instances using the Generator class
hydro_conventional = Generator(
    name="Conventional Hydro",
    source_filter=""""Energy Source Code" = 'WAT' AND "Prime Mover Code" = 'HY'""",
    color_ramp="Blues",
    single_color="dodgerblue",
)

pumped_storage = Generator(
    name="Pumped Storage",
    source_filter=""""Energy Source Code" = 'WAT' AND "Prime Mover Code" = 'PS'""",
    color_ramp="Blues",
    single_color="deepskyblue",
)

coal = Generator(
    name="Coal",
    include=["ANT", "BIT", "CBL", "COG", "LIG", "PC", "RC", "SGC", "SUB", "WC"],
    single_color="sienna",
)

petroleum = Generator(
    name="Petroleum",
    include=[
        "BB",
        "DFO",
        "JF",
        "KER",
        "MF",
        "OG",
        "OL",
        "PC",
        "PG",
        "RFO",
        "SGP",
        "TDF",
        "WO",
    ],
    single_color="darkgray",
)

natural_gas = Generator(name="Natural Gas", include=["NG"])

nuclear = Generator(
    name="Nuclear", include=["NUC"], color_ramp="Purples", single_color="purple"
)

solar = Generator(
    name="Solar",
    include=[
        "SUN",
    ],
    color_ramp="Greens",
    single_color="green",
)

wind = Generator(
    name="Wind",
    include=["WND"],
    color_ramp="Greens",
    single_color="green",
)

other_renewables = Generator(
    name="Other Renewables",
    include=[
        "GEO",
        "AB",
        "BLQ",
        "LFG",
        "MSW",
        "OBG",
        "OBL",
        "OBS",
        "SLW",
        "WDS",
    ],
)

bess = Generator(
    name="BESS",
    source_filter=lambda: """Technology = 'Batteries'""",
    color_ramp="Reds",
    single_color="red",
)

energy_source_code = [
    bess,
    pumped_storage,
    solar,
    wind,
    other_renewables,
    natural_gas,
    hydro_conventional,
    nuclear,
    petroleum,
    coal,
]
