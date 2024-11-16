import asyncio
import math
from typing import Any

from rich.color import Color as RColor
from rich.segment import Segment
from rich.style import Style
from textual import work
from textual.color import Color
from textual.containers import Center, Container, Middle
from textual.events import Resize
from textual.geometry import Region
from textual.reactive import var
from textual.strip import Strip
from textual.widgets import Label, Placeholder


class Ellipse(Container):
    DEFAULT_CSS = """
        Ellipse {
            width: 100%;
            height: 100%;
            align: center middle;
        }
        Ellipse > * {
            max-width: 60%;
            max-height: 60%;
        }
    """
    color = var[Color](Color.parse("red"))

    def __init__(
        self,
        initial: Color | None = None,
        height: int | None = None,
        width: int | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        # where to draw
        self.draw_area: list[list[int]] = []
        # a list that contains list of coordinate that forms each rings
        self.rings: list[list[tuple[int, int]]] = []
        # initial compute
        self.computed = False
        self.ring_colors: list[RColor] = []

        self.width_override = width
        self.height_override = height

        if initial:
            self.color = initial

    def on_resize(self, event: Resize) -> None:
        if len(self.children) == 0:
            inner_region = Region(
                event.size.width // 4, event.size.height // 4, self.width_override or 1, self.height_override or 1
            )
        else:
            inner_region = Region.from_union([child.region for child in self.children])

        self.compute_ellipses(inner_region)

    def compute_ellipses(self, region: Region) -> None:
        self.draw_area = [[0 for _ in range(self.size.width + 1)] for _ in range(self.size.height + 1)]
        self.rings = []
        cx, cy = region.center
        percent = 0.30
        padding_a = percent * region.width
        padding_b = percent * region.height

        max_a = min((region.width / 2) + padding_a, self.size.width)
        max_b = min((region.height / 2) + padding_b, self.size.height)

        a = 1
        b = 1

        ring_no = 1
        # add_a = False
        while a < max_a or b < max_b:
            ring: list[tuple[int, int]] = []

            for row in range(self.size.width):
                for col in range(self.size.height):
                    if ((row - cx) ** 2 / a**2) + ((col - cy) ** 2) / b**2 <= 1:  # noqa: SIM102
                        if self.draw_area[col][row] == 0:
                            ring.append((col, row))
                            self.draw_area[col][row] = ring_no

            self.rings.append(ring)
            ring_no += 1

            # if (add_a and a < max_a) or b >= max_b:
            #     a += 1
            #     if a >= b:
            #         add_a = False
            # elif b < max_b:
            #     b += 1
            #     if b - a > 6:
            #         add_a = True
            a = min(a + 1, max_a)
            b = min(b + 1, max_b)

        self.computed = True
        self.ring_color = [RColor.from_rgb(0, 0, len(self.rings) - idx) for idx, _ in enumerate(self.rings)]
        self.ring_color.insert(0, RColor.from_rgb(0, 0, 0))
        self.refresh()

    @work
    async def update_color(self, color: RColor) -> None:
        for idx, ring in enumerate(self.rings):
            if idx == 0:
                continue
            self.ring_color[idx] = RColor.from_rgb(len(self.rings) - idx, 0, 0)
            # self.ring_color.insert(0, RColor.from_rgb(0, 0, 0))

            # self.refresh(Region.from_union([Region(x, y, 1, 1) for x, y in ring]))
            self.refresh()
            await asyncio.sleep(0.016)
        # for idx, ring in enumerate(self.rings):
        #     self.app.call_after_refresh(self.refresh, *[Region(x, y, 1, 1) for x, y in ring])
        #     await asyncio.sleep(0.1)

    def render_line(self, y: int) -> Strip:
        if not self.computed:
            return Strip.blank(0)
        try:
            row = self.draw_area[y]
        except IndexError:
            return Strip.blank(0)

        segment = [Segment(" ", style=Style(bgcolor=RColor.parse("default"))) for r in row]
        # segment = [Segment(f"{str(r)[-1] if r != 0 else ' '}", style=Style(bgcolor=self.ring_color[r])) for r in row]

        return Strip(segment)


if __name__ == "__main__":
    from textual.app import App, ComposeResult

    class MyApp(App[None]):
        DEFAULT_CSS = """
        Screen Center {
            background: ansi_default;
        }
        Screen Middle {
            background: ansi_default;
        }
        """

        def compose(self) -> ComposeResult:
            with Ellipse(height=19, width=80):
                yield Center(Middle(Label("test")))

        def on_click(self) -> None:
            self.query_one(Ellipse).update_color(RColor.parse("white"))

    app = MyApp(ansi_color=True)
    app.run()
